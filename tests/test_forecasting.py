from decimal import Decimal
from pathlib import Path
import pandas as pd
import pytest

import app as app_module
import retirement_financial_tracking.io.workbook as workbook_io
from retirement_financial_tracking.domain.models import (
    Account,
    AccountType,
    AccountOwner,
    ActualBalanceSnapshot,
    BucketDefinition,
    BucketType,
    CashFlowCategory,
    FilingStatus,
    HouseholdPlan,
    HouseholdSettings,
    Holding,
    Person,
    PersonRole,
    ProjectionSettings,
    RecurringCashFlow,
    RothHandlingPolicy,
    ReturnModelType,
    ReturnScenarioType,
    TaxModelType,
    TaxProjectionMode,
    TaxTreatment,
    WithdrawalAccountTypePriority,
    WithdrawalAllocationMethod,
    WithdrawalOwnerPriority,
    WithdrawalTaxPriority,
)
from retirement_financial_tracking.io import export_case_workbook, import_case_workbook
from retirement_financial_tracking.reporting import (
    build_forecast_report,
    generate_report_assets,
    render_report_markdown,
)
from retirement_financial_tracking.services.forecasting import generate_forecast
from retirement_financial_tracking.ui_helpers import (
    DEFAULT_SAMPLE_NAME,
    EXPORT_MODE_SAVE_UPDATED_COPY,
    EXPORT_MODE_UPDATE_IMPORTED_WORKBOOK,
    UIPlanPayload,
    export_plan_for_ui,
    forecast_for_ui,
    plan_to_ui_values,
    sample_plan,
    sample_plan_names,
    ui_values_to_plan,
)


def test_sample_plan_names_and_bucket_configurations():
    assert sample_plan_names() == [DEFAULT_SAMPLE_NAME, "3-Bucket Sample"]

    two_bucket = sample_plan()
    three_bucket = sample_plan("3-Bucket Sample")

    assert [bucket.bucket_id for bucket in two_bucket.buckets] == ["b1", "b3"]
    assert [bucket.bucket_name for bucket in two_bucket.buckets] == ["Short-Term", "Long-Term"]
    assert two_bucket.buckets[0].replenishment_source_bucket_id == "b3"
    assert two_bucket.settings.return_model_type is ReturnModelType.SIMPLE
    assert [bucket.bucket_id for bucket in three_bucket.buckets] == ["b1", "b2", "b3"]
    assert [bucket.bucket_name for bucket in three_bucket.buckets] == [
        "Short-Term",
        "Intermediate",
        "Long-Term",
    ]
    assert three_bucket.buckets[0].replenishment_source_bucket_id == "b2"
    assert three_bucket.buckets[1].replenishment_source_bucket_id == "b3"
    assert any(bucket.bucket_type is BucketType.INTERMEDIATE for bucket in three_bucket.buckets)
    assert three_bucket.settings.return_model_type is ReturnModelType.SCENARIO_BASED


def test_forecast_rolls_balances_forward_by_year():
    plan = HouseholdPlan(
        plan_id="case-1",
        household_name="Doe Household",
        base_year=2026,
        settings=HouseholdSettings(
            auto_fund_shortfall=False,
            bucket_return_long_term=0.05,
        ),
        people=[
            Person(
                person_id="p1",
                role=PersonRole.PRIMARY,
                display_name="John",
                birth_year=1965,
            ),
        ],
        buckets=[
            BucketDefinition(
                bucket_id="bucket-1",
                bucket_name="Long Term",
                bucket_type=BucketType.LONG_TERM,
                target_amount=Decimal("1000000.00"),
            )
        ],
        accounts=[
            Account(
                account_id="acct-taxable",
                account_name="Taxable Brokerage",
                account_type=AccountType.TAXABLE_BROKERAGE,
                owner=AccountOwner.PRIMARY,
                tax_treatment=TaxTreatment.TAXABLE,
                opening_balance=Decimal("100000.00"),
                expected_annual_return_rate=0.05,
                bucket_id="bucket-1",
            )
        ],
        cash_flows=[
            RecurringCashFlow(
                flow_id="income-ss",
                flow_name="Social Security",
                category=CashFlowCategory.INCOME,
                annual_amount=Decimal("25000.00"),
                start_year=2026,
                end_year=2027,
            ),
            RecurringCashFlow(
                flow_id="expense-living",
                flow_name="Living Expenses",
                category=CashFlowCategory.EXPENSE,
                annual_amount=Decimal("30000.00"),
                start_year=2026,
                end_year=2027,
                annual_growth_rate=0.03,
            ),
            RecurringCashFlow(
                flow_id="contrib-taxable",
                flow_name="Taxable Contribution",
                category=CashFlowCategory.CONTRIBUTION,
                annual_amount=Decimal("12000.00"),
                start_year=2026,
                end_year=2027,
                target_account_id="acct-taxable",
            ),
            RecurringCashFlow(
                flow_id="withdraw-taxable",
                flow_name="Taxable Withdrawal",
                category=CashFlowCategory.WITHDRAWAL,
                annual_amount=Decimal("10000.00"),
                start_year=2026,
                end_year=2027,
                target_account_id="acct-taxable",
            ),
        ],
    )

    result = generate_forecast(
        plan=plan,
        settings=ProjectionSettings(start_year=2026, number_of_years=2),
    )

    assert len(result.rows) == 2
    assert result.rows[0].year == 2026
    assert result.rows[0].net_cash_flow == Decimal("-7000.00")
    assert result.rows[0].total_starting_assets == Decimal("100000.00")
    assert result.rows[0].total_ending_assets == Decimal("107100.00")

    assert result.rows[1].year == 2027
    assert result.rows[1].income_total == Decimal("25000.00")
    assert result.rows[1].expense_total == Decimal("30900.00")
    assert result.rows[1].total_starting_assets == Decimal("107100.00")
    assert result.rows[1].total_ending_assets == Decimal("114555.00")


def test_workbook_round_trip_preserves_plan_data(tmp_path):
    plan = HouseholdPlan(
        plan_id="case-2",
        household_name="Example Household",
        base_year=2026,
        settings=HouseholdSettings(
            state="CT",
            filing_status=FilingStatus.MARRIED_FILING_JOINTLY,
            tax_model=TaxModelType.EFFECTIVE_RATE,
            tax_projection_mode=TaxProjectionMode.INFLATION_ADJUSTED,
            projection_years=30,
            inflation_rate=0.03,
            default_bucket_expense_years=3.0,
            return_model_type=ReturnModelType.SCENARIO_BASED,
            return_scenario_type=ReturnScenarioType.CONSERVATIVE,
            bucket_return_short_term=0.02,
            bucket_return_intermediate=0.04,
            bucket_return_long_term=0.06,
            bucket_return_other=0.03,
            planned_annual_spending=Decimal("96000.00"),
            target_cash_reserve=Decimal("69000.00"),
            federal_effective_tax_rate=0.18,
            state_effective_tax_rate=0.05,
            rmd_start_age=73,
            auto_fund_shortfall=True,
            use_withdrawal_priority_policy=True,
            withdrawal_tax_priority=WithdrawalTaxPriority.TAX_DEFERRED_TAXABLE_TAX_FREE,
            withdrawal_owner_priority=WithdrawalOwnerPriority.SPOUSE_FIRST,
            withdrawal_account_type_priority=WithdrawalAccountTypePriority.RETIREMENT_FIRST,
            withdrawal_allocation_method=WithdrawalAllocationMethod.PRO_RATA,
            roth_handling_policy=RothHandlingPolicy.NORMAL_PRIORITY,
            hsa_contribution_limit_self=Decimal("4300.00"),
            hsa_contribution_limit_family=Decimal("8550.00"),
            hsa_catch_up_amount=Decimal("1000.00"),
            notes="Initial imported household settings.",
        ),
        people=[
            Person(
                person_id="p1",
                role=PersonRole.PRIMARY,
                display_name="Jane",
                birth_year=1970,
                retirement_year=2032,
                life_expectancy=92,
                social_security_claim_age=67.0,
                estimated_monthly_social_security=Decimal("3200.00"),
                pension_start_age=65.0,
                estimated_monthly_pension=Decimal("1000.00"),
                pension_indexed=True,
                medicare_start_year=2035,
                annual_healthcare_premium=Decimal("8400.00"),
                annual_healthcare_out_of_pocket=Decimal("2500.00"),
                hsa_eligible=True,
                desired_annual_hsa_contribution=Decimal("4300.00"),
            ),
            Person(
                person_id="p2",
                role=PersonRole.SPOUSE,
                display_name="Pat",
                birth_year=1972,
                retirement_year=2034,
                life_expectancy=90,
                social_security_claim_age=67.0,
                estimated_monthly_social_security=Decimal("2600.00"),
                pension_start_age=63.0,
                estimated_monthly_pension=Decimal("500.00"),
                medicare_start_year=2037,
                annual_healthcare_premium=Decimal("7200.00"),
                annual_healthcare_out_of_pocket=Decimal("2200.00"),
                desired_annual_hsa_contribution=Decimal("2000.00"),
            ),
        ],
        buckets=[
            BucketDefinition(
                bucket_id="b1",
                bucket_name="Bucket 1",
                bucket_type=BucketType.SHORT_TERM,
                target_amount=Decimal("469000.00"),
                target_years=3,
                replenishment_source_bucket_id="b3",
                notes="Short-term reserve.",
            ),
            BucketDefinition(
                bucket_id="b3",
                bucket_name="Bucket 3",
                bucket_type=BucketType.LONG_TERM,
                target_amount=Decimal("1876065.00"),
                target_years=20,
                notes="Long-term growth capital.",
            ),
        ],
        accounts=[
            Account(
                account_id="acct-1",
                account_name="IRA",
                account_type=AccountType.TRADITIONAL_IRA,
                owner=AccountOwner.PRIMARY,
                custodian="Fidelity",
                tax_treatment=TaxTreatment.TAX_DEFERRED,
                opening_balance=Decimal("750000.00"),
                expected_annual_return_rate=0.06,
                bucket_id="b3",
                contribution_allowed=False,
                withdrawal_allowed=True,
                roth_conversion_source_allowed=True,
            ),
            Account(
                account_id="acct-2",
                account_name="HSA",
                account_type=AccountType.HSA,
                owner=AccountOwner.PRIMARY,
                custodian="Optum",
                tax_treatment=TaxTreatment.HSA,
                opening_balance=Decimal("18000.00"),
                expected_annual_return_rate=0.04,
                bucket_id="b1",
            ),
        ],
        holdings=[
            Holding(
                holding_id="h1",
                account_id="acct-1",
                holding_name="VTI",
                ticker="VTI",
                asset_class="equity",
                market_value=Decimal("400000.00"),
                bucket_id="b3",
                notes="Core US equity allocation.",
            ),
            Holding(
                holding_id="h2",
                account_id="acct-2",
                holding_name="CD Ladder",
                asset_class="cash_equivalent",
                market_value=Decimal("18000.00"),
                bucket_id="b1",
                maturity_year=2027,
                fdic_issuer="Local Bank",
            ),
        ],
        cash_flows=[
            RecurringCashFlow(
                flow_id="tax-1",
                flow_name="Estimated Taxes",
                category=CashFlowCategory.TAX,
                annual_amount=Decimal("9000.00"),
                start_year=2026,
                end_year=2028,
                person_id="p1",
                notes="Annual estimated taxes.",
            ),
            RecurringCashFlow(
                flow_id="expense-1",
                flow_name="Living Expenses",
                category=CashFlowCategory.EXPENSE,
                annual_amount=Decimal("96000.00"),
                start_year=2026,
                end_year=2028,
                annual_growth_rate=0.03,
                notes="Baseline living expenses.",
            ),
        ],
        actual_balance_snapshots=[
            ActualBalanceSnapshot(
                snapshot_id="s1",
                account_id="acct-1",
                as_of_date="2026-01-31",
                balance=Decimal("748500.00"),
                source="Manual entry",
            )
        ],
    )

    path = tmp_path / "case.xlsx"
    export_case_workbook(path, plan)
    imported = import_case_workbook(path)

    assert imported.plan_id == "case-2"
    assert imported.household_name == "Example Household"
    assert imported.settings.filing_status is FilingStatus.MARRIED_FILING_JOINTLY
    assert imported.settings.tax_model is TaxModelType.EFFECTIVE_RATE
    assert imported.settings.tax_projection_mode is TaxProjectionMode.INFLATION_ADJUSTED
    assert imported.settings.target_cash_reserve == Decimal("69000.00")
    assert imported.settings.default_bucket_expense_years == 3.0
    assert imported.settings.rmd_start_age == 73
    assert imported.settings.auto_fund_shortfall is True
    assert imported.settings.use_withdrawal_priority_policy is True
    assert imported.settings.return_model_type is ReturnModelType.SCENARIO_BASED
    assert imported.settings.return_scenario_type is ReturnScenarioType.CONSERVATIVE
    assert (
        imported.settings.withdrawal_tax_priority
        is WithdrawalTaxPriority.TAX_DEFERRED_TAXABLE_TAX_FREE
    )
    assert imported.settings.withdrawal_owner_priority is WithdrawalOwnerPriority.SPOUSE_FIRST
    assert (
        imported.settings.withdrawal_account_type_priority
        is WithdrawalAccountTypePriority.RETIREMENT_FIRST
    )
    assert (
        imported.settings.withdrawal_allocation_method
        is WithdrawalAllocationMethod.PRO_RATA
    )
    assert imported.settings.roth_handling_policy is RothHandlingPolicy.NORMAL_PRIORITY
    assert imported.settings.monte_carlo_simulations == 250
    assert imported.settings.monte_carlo_seed == 42
    assert imported.settings.bucket_return_short_term == 0.02
    assert imported.settings.bucket_return_intermediate == 0.04
    assert imported.settings.bucket_return_long_term == 0.06
    assert imported.settings.bucket_return_other == 0.03
    assert imported.settings.bucket_volatility_short_term == 0.01
    assert imported.settings.bucket_volatility_intermediate == 0.06
    assert imported.settings.bucket_volatility_long_term == 0.12
    assert imported.settings.bucket_volatility_other == 0.08
    assert imported.settings.hsa_contribution_limit_self == Decimal("4300.00")
    assert len(imported.people) == 2
    assert imported.people[0].estimated_monthly_social_security == Decimal("3200.00")
    assert imported.people[0].estimated_monthly_pension == Decimal("1000.00")
    assert imported.people[0].desired_annual_hsa_contribution == Decimal("4300.00")
    assert imported.buckets[0].bucket_name == "Bucket 1"
    assert imported.buckets[0].replenishment_source_bucket_id == "b3"
    assert imported.accounts[0].account_name == "IRA"
    assert imported.accounts[0].account_type is AccountType.TRADITIONAL_IRA
    assert imported.accounts[0].roth_conversion_source_allowed is True
    assert imported.holdings[1].fdic_issuer == "Local Bank"
    assert imported.cash_flows[0].category is CashFlowCategory.TAX
    assert imported.cash_flows[0].person_id == "p1"
    assert imported.actual_balance_snapshots[0].balance == Decimal("748500.00")


def test_import_case_workbook_reads_tabular_sheets_by_header_name(tmp_path):
    plan = sample_plan("3-Bucket Sample")
    path = tmp_path / "header-reorder.xlsx"
    export_case_workbook(path, plan)

    from openpyxl import load_workbook

    workbook = load_workbook(path)
    accounts_sheet = workbook["Accounts"]
    original_rows = list(accounts_sheet.iter_rows(values_only=True))
    reordered_headers = [
        "tax_treatment",
        "bucket_id",
        "account_name",
        "account_id",
        "owner",
        "opening_balance",
        "account_type",
        "expected_annual_return_rate",
        "custodian",
        "withdrawal_allowed",
        "contribution_allowed",
        "roth_conversion_source_allowed",
    ]
    header_index = {header: index for index, header in enumerate(original_rows[0])}
    accounts_sheet.delete_rows(1, accounts_sheet.max_row)
    accounts_sheet.append(reordered_headers)
    for row in original_rows[1:]:
        accounts_sheet.append([row[header_index[header]] for header in reordered_headers])
    workbook.save(path)

    imported = import_case_workbook(path)

    ira_account = next(account for account in imported.accounts if account.account_id == "acct-1")
    assert ira_account.account_name == "Traditional IRA"
    assert ira_account.tax_treatment is TaxTreatment.TAX_DEFERRED
    assert ira_account.bucket_id == "b3"
    assert ira_account.owner is AccountOwner.PRIMARY
    assert ira_account.opening_balance == Decimal("1200000.00")


def test_household_plan_rejects_duplicate_account_ids():
    with pytest.raises(ValueError, match="Duplicate account IDs are not allowed: acct-1"):
        HouseholdPlan(
            plan_id="dup-case",
            household_name="Duplicate IDs",
            base_year=2026,
            settings=HouseholdSettings(),
            people=[
                Person(
                    person_id="p1",
                    role=PersonRole.PRIMARY,
                    display_name="Taylor",
                    birth_year=1970,
                ),
            ],
            accounts=[
                Account(
                    account_id="acct-1",
                    account_name="IRA A",
                    account_type=AccountType.TRADITIONAL_IRA,
                    owner=AccountOwner.PRIMARY,
                    tax_treatment=TaxTreatment.TAX_DEFERRED,
                    opening_balance=Decimal("1000.00"),
                ),
                Account(
                    account_id="acct-1",
                    account_name="IRA B",
                    account_type=AccountType.ROTH_IRA,
                    owner=AccountOwner.PRIMARY,
                    tax_treatment=TaxTreatment.TAX_FREE,
                    opening_balance=Decimal("2000.00"),
                ),
            ],
        )


def test_forecast_uses_actual_balances_and_derived_retirement_inputs():
    plan = HouseholdPlan(
        plan_id="case-3",
        household_name="Derived Inputs Household",
        base_year=2026,
        settings=HouseholdSettings(
            state="CT",
            filing_status=FilingStatus.MARRIED_FILING_JOINTLY,
            projection_years=30,
            inflation_rate=0.02,
            planned_annual_spending=Decimal("50000.00"),
            federal_effective_tax_rate=0.10,
            state_effective_tax_rate=0.05,
            auto_fund_shortfall=False,
            hsa_contribution_limit_self=Decimal("4300.00"),
        ),
        people=[
            Person(
                person_id="p1",
                role=PersonRole.PRIMARY,
                display_name="Alex",
                birth_year=1960,
                social_security_claim_age=65.0,
                estimated_monthly_social_security=Decimal("2000.00"),
                medicare_start_year=2026,
                annual_healthcare_premium=Decimal("3000.00"),
                annual_healthcare_out_of_pocket=Decimal("1000.00"),
            )
        ],
        accounts=[
            Account(
                account_id="acct-1",
                account_name="Traditional IRA",
                account_type=AccountType.TRADITIONAL_IRA,
                owner=AccountOwner.PRIMARY,
                tax_treatment=TaxTreatment.TAX_DEFERRED,
                opening_balance=Decimal("100000.00"),
                expected_annual_return_rate=0.05,
            )
        ],
        cash_flows=[
            RecurringCashFlow(
                flow_id="withdraw-1",
                flow_name="IRA Withdrawal",
                category=CashFlowCategory.WITHDRAWAL,
                annual_amount=Decimal("10000.00"),
                start_year=2026,
                end_year=2026,
                target_account_id="acct-1",
            )
        ],
        actual_balance_snapshots=[
            ActualBalanceSnapshot(
                snapshot_id="snap-1",
                account_id="acct-1",
                as_of_date="2025-12-31",
                balance=Decimal("88000.00"),
                source="Older snapshot",
            ),
            ActualBalanceSnapshot(
                snapshot_id="snap-2",
                account_id="acct-1",
                as_of_date="2026-01-31",
                balance=Decimal("90000.00"),
                source="Latest snapshot",
            ),
        ],
    )

    result = generate_forecast(
        plan=plan,
        settings=ProjectionSettings(start_year=2026, number_of_years=2),
    )

    assert result.rows[0].total_starting_assets == Decimal("90000.00")
    assert result.rows[0].social_security_total == Decimal("24000.00")
    assert result.rows[0].living_expense_total == Decimal("50000.00")
    assert result.rows[0].healthcare_total == Decimal("4000.00")
    assert result.rows[0].derived_tax_total == Decimal("5100.00")
    assert result.rows[0].tax_total == Decimal("5100.00")
    assert result.rows[0].net_cash_flow == Decimal("-25100.00")
    assert result.rows[0].total_ending_assets == Decimal("84000.00")

    assert result.rows[1].living_expense_total == Decimal("51000.00")
    assert result.rows[1].derived_tax_total == Decimal("3600.00")
    assert result.rows[1].total_starting_assets == Decimal("84000.00")
    assert result.rows[1].total_ending_assets == Decimal("88200.00")


def test_ui_values_to_plan_accepts_gradio_dataframe_values():
    original = HouseholdPlan(
        plan_id="case-4",
        household_name="UI Household",
        base_year=2026,
        settings=HouseholdSettings(
            state="CT",
            filing_status=FilingStatus.MARRIED_FILING_JOINTLY,
            projection_years=5,
            inflation_rate=0.03,
            planned_annual_spending=Decimal("40000.00"),
            use_withdrawal_priority_policy=True,
            withdrawal_tax_priority=WithdrawalTaxPriority.TAX_DEFERRED_TAXABLE_TAX_FREE,
            withdrawal_owner_priority=WithdrawalOwnerPriority.OLDER_FIRST,
            withdrawal_account_type_priority=WithdrawalAccountTypePriority.LIQUID_FIRST,
            withdrawal_allocation_method=WithdrawalAllocationMethod.PRO_RATA,
            roth_handling_policy=RothHandlingPolicy.LAST_RESORT,
        ),
        people=[
            Person(
                person_id="p1",
                role=PersonRole.PRIMARY,
                display_name="Casey",
                birth_year=1970,
            )
        ],
        buckets=[
            BucketDefinition(
                bucket_id="b1",
                bucket_name="Bucket 1",
                bucket_type=BucketType.SHORT_TERM,
                target_amount=Decimal("10000.00"),
            )
        ],
        accounts=[
            Account(
                account_id="a1",
                account_name="Brokerage",
                account_type=AccountType.TAXABLE_BROKERAGE,
                owner=AccountOwner.PRIMARY,
                tax_treatment=TaxTreatment.TAXABLE,
                opening_balance=Decimal("1000.00"),
                bucket_id="b1",
            )
        ],
        holdings=[
            Holding(
                holding_id="h1",
                account_id="a1",
                holding_name="Cash",
                market_value=Decimal("1000.00"),
            )
        ],
        cash_flows=[
            RecurringCashFlow(
                flow_id="cf1",
                flow_name="Expense",
                category=CashFlowCategory.EXPENSE,
                annual_amount=Decimal("100.00"),
                start_year=2026,
                end_year=2026,
            )
        ],
        actual_balance_snapshots=[
            ActualBalanceSnapshot(
                snapshot_id="s1",
                account_id="a1",
                as_of_date="2026-01-01",
                balance=Decimal("1000.00"),
            )
        ],
    )

    values = plan_to_ui_values(original)
    restored = ui_values_to_plan(
        UIPlanPayload.from_mapping(
            {
                **values,
                "people": pd.DataFrame(values["people"]),
                "buckets": pd.DataFrame(values["buckets"]),
                "accounts": pd.DataFrame(values["accounts"]),
                "cash_flows": pd.DataFrame(values["cash_flows"]),
                "holdings": pd.DataFrame(values["holdings"]),
                "snapshots": pd.DataFrame(values["snapshots"]),
            }
        )
    )

    assert restored.plan_id == "case-4"
    assert restored.people[0].display_name == "Casey"
    assert restored.accounts[0].account_name == "Brokerage"
    assert restored.cash_flows[0].annual_amount == Decimal("100.00")
    assert restored.settings.default_bucket_expense_years == original.settings.default_bucket_expense_years
    assert restored.settings.return_model_type == original.settings.return_model_type
    assert restored.settings.tax_model == original.settings.tax_model
    assert restored.settings.tax_projection_mode == original.settings.tax_projection_mode
    assert restored.settings.return_scenario_type == original.settings.return_scenario_type
    assert restored.settings.monte_carlo_simulations == original.settings.monte_carlo_simulations
    assert restored.settings.monte_carlo_seed == original.settings.monte_carlo_seed
    assert (
        restored.settings.monte_carlo_depletion_target_year
        == original.settings.monte_carlo_depletion_target_year
    )
    assert (
        restored.settings.monte_carlo_depletion_target_age
        == original.settings.monte_carlo_depletion_target_age
    )
    assert restored.settings.bucket_return_short_term == original.settings.bucket_return_short_term
    assert restored.settings.bucket_volatility_long_term == original.settings.bucket_volatility_long_term
    assert restored.settings.use_withdrawal_priority_policy is True
    assert (
        restored.settings.withdrawal_tax_priority
        is WithdrawalTaxPriority.TAX_DEFERRED_TAXABLE_TAX_FREE
    )
    assert restored.settings.withdrawal_owner_priority is WithdrawalOwnerPriority.OLDER_FIRST
    assert (
        restored.settings.withdrawal_account_type_priority
        is WithdrawalAccountTypePriority.LIQUID_FIRST
    )
    assert (
        restored.settings.withdrawal_allocation_method
        is WithdrawalAllocationMethod.PRO_RATA
    )
    assert restored.settings.roth_handling_policy is RothHandlingPolicy.LAST_RESORT


def test_ui_plan_payload_rejects_wrong_value_count():
    with pytest.raises(ValueError, match="Expected .* UI plan values"):
        UIPlanPayload.from_ordered_values(["only-one-value"])


def test_monte_carlo_forecast_returns_seeded_percentile_summary():
    plan = HouseholdPlan(
        plan_id="case-mc-1",
        household_name="Monte Carlo Household",
        base_year=2026,
        settings=HouseholdSettings(
            projection_years=3,
            return_model_type=ReturnModelType.MONTE_CARLO,
            monte_carlo_simulations=50,
            monte_carlo_seed=7,
            bucket_return_long_term=0.06,
            bucket_volatility_long_term=0.10,
            auto_fund_shortfall=False,
        ),
        people=[
            Person(
                person_id="p1",
                role=PersonRole.PRIMARY,
                display_name="Taylor",
                birth_year=1965,
            ),
        ],
        buckets=[
            BucketDefinition(
                bucket_id="bucket-1",
                bucket_name="Long Term",
                bucket_type=BucketType.LONG_TERM,
                target_amount=Decimal("0.00"),
            )
        ],
        accounts=[
            Account(
                account_id="acct-1",
                account_name="Brokerage",
                account_type=AccountType.TAXABLE_BROKERAGE,
                owner=AccountOwner.PRIMARY,
                tax_treatment=TaxTreatment.TAXABLE,
                opening_balance=Decimal("100000.00"),
                expected_annual_return_rate=0.06,
                bucket_id="bucket-1",
            )
        ],
    )

    result = generate_forecast(
        plan=plan,
        settings=ProjectionSettings(start_year=2026, number_of_years=3),
    )

    assert result.return_model_type is ReturnModelType.MONTE_CARLO
    assert result.monte_carlo_simulations == 50
    assert result.monte_carlo_seed == 7
    assert len(result.rows) == 3
    assert result.final_total_assets_p10 is not None
    assert result.final_total_assets_median is not None
    assert result.final_total_assets_p90 is not None
    assert result.final_total_assets_p10 <= result.final_total_assets_median <= result.final_total_assets_p90
    assert result.final_total_assets == result.rows[-1].total_ending_assets


def test_forecast_summary_reports_depletion_year_when_assets_run_out():
    plan = HouseholdPlan(
        plan_id="case-summary-1",
        household_name="Summary Household",
        base_year=2026,
        settings=HouseholdSettings(
            projection_years=3,
            planned_annual_spending=Decimal("60000.00"),
            bucket_return_long_term=0.0,
            auto_fund_shortfall=True,
        ),
        people=[
            Person(
                person_id="p1",
                role=PersonRole.PRIMARY,
                display_name="Taylor",
                birth_year=1965,
            ),
        ],
        buckets=[
            BucketDefinition(
                bucket_id="bucket-1",
                bucket_name="Long Term",
                bucket_type=BucketType.LONG_TERM,
                target_amount=Decimal("0.00"),
            )
        ],
        accounts=[
            Account(
                account_id="acct-1",
                account_name="Brokerage",
                account_type=AccountType.TAXABLE_BROKERAGE,
                owner=AccountOwner.PRIMARY,
                tax_treatment=TaxTreatment.TAXABLE,
                opening_balance=Decimal("100000.00"),
                expected_annual_return_rate=0.0,
                bucket_id="bucket-1",
            )
        ],
    )

    _, _, summary = forecast_for_ui(plan)

    assert "Money lasts until year: 2027" in summary


def test_forecast_summary_reports_projection_horizon_when_assets_do_not_run_out():
    plan = HouseholdPlan(
        plan_id="case-summary-2",
        household_name="Summary Household",
        base_year=2026,
        settings=HouseholdSettings(
            projection_years=3,
            planned_annual_spending=Decimal("0.00"),
            bucket_return_long_term=0.05,
            auto_fund_shortfall=False,
        ),
        people=[
            Person(
                person_id="p1",
                role=PersonRole.PRIMARY,
                display_name="Taylor",
                birth_year=1965,
            ),
        ],
        buckets=[
            BucketDefinition(
                bucket_id="bucket-1",
                bucket_name="Long Term",
                bucket_type=BucketType.LONG_TERM,
                target_amount=Decimal("0.00"),
            )
        ],
        accounts=[
            Account(
                account_id="acct-1",
                account_name="Brokerage",
                account_type=AccountType.TAXABLE_BROKERAGE,
                owner=AccountOwner.PRIMARY,
                tax_treatment=TaxTreatment.TAXABLE,
                opening_balance=Decimal("100000.00"),
                expected_annual_return_rate=0.05,
                bucket_id="bucket-1",
            )
        ],
    )

    _, _, summary = forecast_for_ui(plan)

    assert "Money lasts through year: 2028" in summary


def test_monte_carlo_summary_reports_depletion_probability_by_year_and_age():
    plan = HouseholdPlan(
        plan_id="case-summary-3",
        household_name="Monte Carlo Summary Household",
        base_year=2026,
        settings=HouseholdSettings(
            projection_years=3,
            return_model_type=ReturnModelType.MONTE_CARLO,
            monte_carlo_simulations=20,
            monte_carlo_seed=9,
            monte_carlo_depletion_target_year=2027,
            monte_carlo_depletion_target_age=62,
            planned_annual_spending=Decimal("60000.00"),
            bucket_return_long_term=0.0,
            bucket_volatility_long_term=0.0,
            auto_fund_shortfall=True,
        ),
        people=[
            Person(
                person_id="p1",
                role=PersonRole.PRIMARY,
                display_name="Taylor",
                birth_year=1965,
            ),
        ],
        buckets=[
            BucketDefinition(
                bucket_id="bucket-1",
                bucket_name="Long Term",
                bucket_type=BucketType.LONG_TERM,
                target_amount=Decimal("0.00"),
            )
        ],
        accounts=[
            Account(
                account_id="acct-1",
                account_name="Brokerage",
                account_type=AccountType.TAXABLE_BROKERAGE,
                owner=AccountOwner.PRIMARY,
                tax_treatment=TaxTreatment.TAXABLE,
                opening_balance=Decimal("100000.00"),
                expected_annual_return_rate=0.0,
                bucket_id="bucket-1",
            )
        ],
    )

    _, _, summary = forecast_for_ui(plan)

    assert "Probability of depletion by year 2027: 100%" in summary
    assert "Probability of depletion by age 62 (Taylor, year 2027): 100%" in summary


def test_auto_funded_tax_deferred_withdrawals_increase_derived_taxes():
    plan = HouseholdPlan(
        plan_id="case-tax-sequencing",
        household_name="Tax Sequencing Household",
        base_year=2026,
        settings=HouseholdSettings(
            planned_annual_spending=Decimal("1000.00"),
            federal_effective_tax_rate=0.10,
            state_effective_tax_rate=0.00,
            auto_fund_shortfall=True,
            bucket_return_long_term=0.0,
        ),
        people=[
            Person(
                person_id="p1",
                role=PersonRole.PRIMARY,
                display_name="Taylor",
                birth_year=1965,
            ),
        ],
        buckets=[
            BucketDefinition(
                bucket_id="bucket-1",
                bucket_name="Long Term",
                bucket_type=BucketType.LONG_TERM,
            )
        ],
        accounts=[
            Account(
                account_id="acct-1",
                account_name="Traditional IRA",
                account_type=AccountType.TRADITIONAL_IRA,
                owner=AccountOwner.PRIMARY,
                tax_treatment=TaxTreatment.TAX_DEFERRED,
                opening_balance=Decimal("2000.00"),
                expected_annual_return_rate=0.0,
                bucket_id="bucket-1",
            )
        ],
    )

    result = generate_forecast(
        plan=plan,
        settings=ProjectionSettings(start_year=2026, number_of_years=1),
    )

    row = result.rows[0]
    account_row = result.account_rows[0]

    assert row.derived_tax_total == Decimal("111.11")
    assert row.auto_funding_withdrawal_total == Decimal("1111.11")
    assert row.net_cash_flow == Decimal("0.00")
    assert account_row.end_balance == Decimal("888.89")


def test_forecast_derives_hsa_contributions_and_reduces_tax_base():
    plan = HouseholdPlan(
        plan_id="case-6",
        household_name="HSA Household",
        base_year=2026,
        settings=HouseholdSettings(
            planned_annual_spending=Decimal("0.00"),
            federal_effective_tax_rate=0.10,
            state_effective_tax_rate=0.05,
            auto_fund_shortfall=False,
            hsa_contribution_limit_self=Decimal("4300.00"),
            hsa_catch_up_amount=Decimal("1000.00"),
        ),
        people=[
            Person(
                person_id="p1",
                role=PersonRole.PRIMARY,
                display_name="HSA Person",
                birth_year=1960,
                hsa_eligible=True,
                desired_annual_hsa_contribution=Decimal("7000.00"),
                medicare_start_year=2028,
            )
        ],
        accounts=[
            Account(
                account_id="hsa-1",
                account_name="HSA",
                account_type=AccountType.HSA,
                owner=AccountOwner.PRIMARY,
                tax_treatment=TaxTreatment.HSA,
                opening_balance=Decimal("10000.00"),
                expected_annual_return_rate=0.0,
            ),
            Account(
                account_id="tax-1",
                account_name="Brokerage",
                account_type=AccountType.TAXABLE_BROKERAGE,
                owner=AccountOwner.PRIMARY,
                tax_treatment=TaxTreatment.TAXABLE,
                opening_balance=Decimal("1000.00"),
                expected_annual_return_rate=0.0,
            ),
        ],
        cash_flows=[
            RecurringCashFlow(
                flow_id="income-1",
                flow_name="Consulting",
                category=CashFlowCategory.INCOME,
                annual_amount=Decimal("50000.00"),
                start_year=2026,
                end_year=2028,
            )
        ],
    )

    result = generate_forecast(
        plan=plan,
        settings=ProjectionSettings(start_year=2026, number_of_years=3),
    )

    assert result.rows[0].hsa_contribution_total == Decimal("5300.00")
    assert result.rows[0].contribution_total == Decimal("5300.00")
    assert result.rows[0].derived_tax_total == Decimal("6705.00")
    assert result.account_rows[0].account_id == "hsa-1"
    assert result.account_rows[0].contributions == Decimal("5300.00")
    assert result.rows[2].hsa_contribution_total == Decimal("0.00")


def test_forecast_supports_bracket_based_federal_tax():
    plan = HouseholdPlan(
        plan_id="case-tax-brackets-fed",
        household_name="Bracket Federal Household",
        base_year=2026,
        settings=HouseholdSettings(
            state="TX",
            filing_status=FilingStatus.SINGLE,
            tax_model=TaxModelType.BRACKET_BASED,
            tax_projection_mode=TaxProjectionMode.STATIC,
            planned_annual_spending=Decimal("0.00"),
            auto_fund_shortfall=False,
        ),
        people=[
            Person(
                person_id="p1",
                role=PersonRole.PRIMARY,
                display_name="Taylor",
                birth_year=1970,
            )
        ],
        cash_flows=[
            RecurringCashFlow(
                flow_id="income-1",
                flow_name="Consulting",
                category=CashFlowCategory.INCOME,
                annual_amount=Decimal("50000.00"),
                start_year=2026,
                end_year=2026,
            )
        ],
    )

    result = generate_forecast(
        plan=plan,
        settings=ProjectionSettings(start_year=2026, number_of_years=1),
    )

    assert result.rows[0].derived_tax_total == Decimal("4016.00")
    assert result.rows[0].tax_total == Decimal("4016.00")


def test_forecast_supports_bracket_based_federal_and_connecticut_tax():
    plan = HouseholdPlan(
        plan_id="case-tax-brackets-ct",
        household_name="Bracket CT Household",
        base_year=2026,
        settings=HouseholdSettings(
            state="CT",
            filing_status=FilingStatus.MARRIED_FILING_JOINTLY,
            tax_model=TaxModelType.BRACKET_BASED,
            tax_projection_mode=TaxProjectionMode.STATIC,
            planned_annual_spending=Decimal("0.00"),
            auto_fund_shortfall=False,
        ),
        people=[
            Person(
                person_id="p1",
                role=PersonRole.PRIMARY,
                display_name="Alex",
                birth_year=1970,
            )
        ],
        cash_flows=[
            RecurringCashFlow(
                flow_id="income-1",
                flow_name="Salary",
                category=CashFlowCategory.INCOME,
                annual_amount=Decimal("100000.00"),
                start_year=2026,
                end_year=2026,
            )
        ],
    )

    result = generate_forecast(
        plan=plan,
        settings=ProjectionSettings(start_year=2026, number_of_years=1),
    )

    assert result.rows[0].derived_tax_total == Decimal("11152.00")
    assert result.rows[0].tax_total == Decimal("11152.00")


def test_forecast_supports_inflation_adjusted_bracket_based_taxes():
    plan = HouseholdPlan(
        plan_id="case-tax-brackets-ct-inflation",
        household_name="Bracket CT Inflation Household",
        base_year=2026,
        settings=HouseholdSettings(
            state="CT",
            filing_status=FilingStatus.MARRIED_FILING_JOINTLY,
            tax_model=TaxModelType.BRACKET_BASED,
            tax_projection_mode=TaxProjectionMode.INFLATION_ADJUSTED,
            inflation_rate=0.03,
            planned_annual_spending=Decimal("0.00"),
            auto_fund_shortfall=False,
        ),
        people=[
            Person(
                person_id="p1",
                role=PersonRole.PRIMARY,
                display_name="Alex",
                birth_year=1970,
            )
        ],
        cash_flows=[
            RecurringCashFlow(
                flow_id="income-1",
                flow_name="Salary",
                category=CashFlowCategory.INCOME,
                annual_amount=Decimal("100000.00"),
                start_year=2026,
                end_year=2026,
            )
        ],
    )

    result = generate_forecast(
        plan=plan,
        settings=ProjectionSettings(start_year=2026, number_of_years=1),
    )

    assert result.rows[0].derived_tax_total == Decimal("10856.76")
    assert result.rows[0].tax_total == Decimal("10856.76")


def test_forecast_automatically_uses_hsa_for_healthcare_expenses():
    plan = HouseholdPlan(
        plan_id="case-7",
        household_name="HSA Healthcare Household",
        base_year=2026,
        settings=HouseholdSettings(
            planned_annual_spending=Decimal("0.00"),
            auto_fund_shortfall=False,
        ),
        people=[
            Person(
                person_id="p1",
                role=PersonRole.PRIMARY,
                display_name="Jordan",
                birth_year=1970,
                medicare_start_year=2026,
                annual_healthcare_premium=Decimal("3000.00"),
                annual_healthcare_out_of_pocket=Decimal("1000.00"),
            )
        ],
        accounts=[
            Account(
                account_id="hsa-1",
                account_name="HSA",
                account_type=AccountType.HSA,
                owner=AccountOwner.PRIMARY,
                tax_treatment=TaxTreatment.HSA,
                opening_balance=Decimal("5000.00"),
                expected_annual_return_rate=0.0,
            )
        ],
    )

    result = generate_forecast(
        plan=plan,
        settings=ProjectionSettings(start_year=2026, number_of_years=1),
    )

    row = result.rows[0]
    account_row = result.account_rows[0]
    assert row.healthcare_total == Decimal("4000.00")
    assert row.hsa_healthcare_withdrawal_total == Decimal("4000.00")
    assert row.withdrawal_total == Decimal("4000.00")
    assert row.net_cash_flow == Decimal("0.00")
    assert row.total_ending_assets == Decimal("1000.00")
    assert account_row.hsa_healthcare_withdrawals == Decimal("4000.00")
    assert account_row.end_balance == Decimal("1000.00")


def test_forecast_derives_pension_rmd_and_bucket_funding():
    plan = HouseholdPlan(
        plan_id="case-5",
        household_name="RMD Household",
        base_year=2026,
        settings=HouseholdSettings(
            planned_annual_spending=Decimal("50000.00"),
            auto_fund_shortfall=True,
            rmd_start_age=73,
            bucket_return_short_term=0.0,
            bucket_return_intermediate=0.0,
            bucket_return_long_term=0.0,
            bucket_return_other=0.0,
        ),
        people=[
            Person(
                person_id="p1",
                role=PersonRole.PRIMARY,
                display_name="Robin",
                birth_year=1950,
                pension_start_age=65.0,
                estimated_monthly_pension=Decimal("1000.00"),
            )
        ],
        buckets=[
            BucketDefinition(
                bucket_id="b1",
                bucket_name="Bucket 1",
                bucket_type=BucketType.SHORT_TERM,
                target_amount=Decimal("20000.00"),
            ),
            BucketDefinition(
                bucket_id="b3",
                bucket_name="Bucket 3",
                bucket_type=BucketType.LONG_TERM,
                target_amount=Decimal("100000.00"),
            ),
        ],
        accounts=[
            Account(
                account_id="cash-1",
                account_name="Cash",
                account_type=AccountType.CASH,
                owner=AccountOwner.PRIMARY,
                tax_treatment=TaxTreatment.TAXABLE,
                opening_balance=Decimal("20000.00"),
                expected_annual_return_rate=0.0,
                bucket_id="b1",
            ),
            Account(
                account_id="ira-1",
                account_name="IRA",
                account_type=AccountType.TRADITIONAL_IRA,
                owner=AccountOwner.PRIMARY,
                tax_treatment=TaxTreatment.TAX_DEFERRED,
                opening_balance=Decimal("100000.00"),
                expected_annual_return_rate=0.0,
                bucket_id="b3",
            ),
        ],
    )

    result = generate_forecast(
        plan=plan,
        settings=ProjectionSettings(start_year=2026, number_of_years=1),
    )

    row = result.rows[0]
    assert row.pension_total == Decimal("12000.00")
    assert row.rmd_withdrawal_total == Decimal("4219.41")
    assert row.auto_funding_withdrawal_total == Decimal("33780.59")
    assert row.withdrawal_total == Decimal("38000.00")
    assert row.short_term_ending_assets == Decimal("0.00")
    assert row.long_term_ending_assets == Decimal("82000.00")
    assert row.net_cash_flow == Decimal("0.00")
    assert row.total_ending_assets == Decimal("82000.00")


def test_forecast_uses_bucket_return_assumptions_for_bucketed_accounts():
    plan = HouseholdPlan(
        plan_id="case-bucket-rates",
        household_name="Bucket Rates Household",
        base_year=2026,
        settings=HouseholdSettings(
            auto_fund_shortfall=False,
            bucket_return_short_term=0.01,
            bucket_return_intermediate=0.04,
            bucket_return_long_term=0.07,
            bucket_return_other=0.02,
        ),
        people=[
            Person(
                person_id="p1",
                role=PersonRole.PRIMARY,
                display_name="Jordan",
                birth_year=1965,
            ),
        ],
        buckets=[
            BucketDefinition(
                bucket_id="short",
                bucket_name="Short",
                bucket_type=BucketType.SHORT_TERM,
            ),
            BucketDefinition(
                bucket_id="long",
                bucket_name="Long",
                bucket_type=BucketType.LONG_TERM,
            ),
        ],
        accounts=[
            Account(
                account_id="cash-1",
                account_name="Cash Bucket",
                account_type=AccountType.CASH,
                owner=AccountOwner.PRIMARY,
                tax_treatment=TaxTreatment.TAXABLE,
                opening_balance=Decimal("1000.00"),
                expected_annual_return_rate=0.99,
                bucket_id="short",
            ),
            Account(
                account_id="growth-1",
                account_name="Growth Bucket",
                account_type=AccountType.TAXABLE_BROKERAGE,
                owner=AccountOwner.PRIMARY,
                tax_treatment=TaxTreatment.TAXABLE,
                opening_balance=Decimal("1000.00"),
                expected_annual_return_rate=0.99,
                bucket_id="long",
            ),
        ],
    )

    result = generate_forecast(
        plan=plan,
        settings=ProjectionSettings(start_year=2026, number_of_years=1),
    )

    cash_row = next(row for row in result.account_rows if row.account_id == "cash-1")
    growth_row = next(row for row in result.account_rows if row.account_id == "growth-1")

    assert cash_row.bucket_type is BucketType.SHORT_TERM
    assert cash_row.effective_annual_return_rate == 0.01
    assert cash_row.investment_growth == Decimal("10.00")
    assert growth_row.bucket_type is BucketType.LONG_TERM
    assert growth_row.effective_annual_return_rate == 0.07
    assert growth_row.investment_growth == Decimal("70.00")


def test_forecast_uses_yearly_scenario_returns_for_bucketed_accounts():
    plan = HouseholdPlan(
        plan_id="case-scenario-rates",
        household_name="Scenario Rates Household",
        base_year=2026,
        settings=HouseholdSettings(
            auto_fund_shortfall=False,
            return_model_type=ReturnModelType.SCENARIO_BASED,
            return_scenario_type=ReturnScenarioType.BAD_FIRST_5_YEARS,
            bucket_return_long_term=0.99,
        ),
        people=[
            Person(
                person_id="p1",
                role=PersonRole.PRIMARY,
                display_name="Morgan",
                birth_year=1965,
            ),
        ],
        buckets=[
            BucketDefinition(
                bucket_id="long",
                bucket_name="Long",
                bucket_type=BucketType.LONG_TERM,
            ),
        ],
        accounts=[
            Account(
                account_id="growth-1",
                account_name="Growth Bucket",
                account_type=AccountType.TAXABLE_BROKERAGE,
                owner=AccountOwner.PRIMARY,
                tax_treatment=TaxTreatment.TAXABLE,
                opening_balance=Decimal("1000.00"),
                expected_annual_return_rate=0.99,
                bucket_id="long",
            ),
        ],
    )

    result = generate_forecast(
        plan=plan,
        settings=ProjectionSettings(start_year=2026, number_of_years=2),
    )

    first_year = result.account_rows[0]
    second_year = result.account_rows[1]

    assert first_year.effective_annual_return_rate == -0.18
    assert first_year.investment_growth == Decimal("-180.00")
    assert first_year.end_balance == Decimal("820.00")
    assert second_year.effective_annual_return_rate == -0.10
    assert second_year.start_balance == Decimal("820.00")
    assert second_year.investment_growth == Decimal("-82.00")
    assert second_year.end_balance == Decimal("738.00")


def test_withdrawal_priority_can_prefer_older_spouse_within_same_bucket():
    plan = HouseholdPlan(
        plan_id="case-withdraw-older-first",
        household_name="Older First Household",
        base_year=2026,
        settings=HouseholdSettings(
            planned_annual_spending=Decimal("15000.00"),
            bucket_return_long_term=0.0,
            auto_fund_shortfall=True,
            use_withdrawal_priority_policy=True,
            withdrawal_tax_priority=WithdrawalTaxPriority.TAX_DEFERRED_TAXABLE_TAX_FREE,
            withdrawal_owner_priority=WithdrawalOwnerPriority.OLDER_FIRST,
            withdrawal_account_type_priority=WithdrawalAccountTypePriority.NO_PREFERENCE,
            withdrawal_allocation_method=WithdrawalAllocationMethod.DRAIN_ONE_THEN_NEXT,
            roth_handling_policy=RothHandlingPolicy.LAST_RESORT,
        ),
        people=[
            Person(
                person_id="p1",
                role=PersonRole.PRIMARY,
                display_name="Younger Primary",
                birth_year=1970,
            ),
            Person(
                person_id="p2",
                role=PersonRole.SPOUSE,
                display_name="Older Spouse",
                birth_year=1960,
            ),
        ],
        buckets=[
            BucketDefinition(
                bucket_id="b3",
                bucket_name="Long-Term",
                bucket_type=BucketType.LONG_TERM,
            ),
        ],
        accounts=[
            Account(
                account_id="ira-primary",
                account_name="Primary IRA",
                account_type=AccountType.TRADITIONAL_IRA,
                owner=AccountOwner.PRIMARY,
                tax_treatment=TaxTreatment.TAX_DEFERRED,
                opening_balance=Decimal("10000.00"),
                bucket_id="b3",
            ),
            Account(
                account_id="ira-spouse",
                account_name="Spouse IRA",
                account_type=AccountType.TRADITIONAL_IRA,
                owner=AccountOwner.SPOUSE,
                tax_treatment=TaxTreatment.TAX_DEFERRED,
                opening_balance=Decimal("10000.00"),
                bucket_id="b3",
            ),
        ],
    )

    result = generate_forecast(
        plan=plan,
        settings=ProjectionSettings(start_year=2026, number_of_years=1),
    )

    primary_row = next(row for row in result.account_rows if row.account_id == "ira-primary")
    spouse_row = next(row for row in result.account_rows if row.account_id == "ira-spouse")

    assert spouse_row.auto_funding_withdrawals == Decimal("10000.00")
    assert primary_row.auto_funding_withdrawals == Decimal("5000.00")


def test_withdrawal_priority_can_prefer_tax_deferred_before_taxable():
    plan = HouseholdPlan(
        plan_id="case-withdraw-tax-priority",
        household_name="Tax Priority Household",
        base_year=2026,
        settings=HouseholdSettings(
            planned_annual_spending=Decimal("12000.00"),
            bucket_return_long_term=0.0,
            auto_fund_shortfall=True,
            use_withdrawal_priority_policy=True,
            withdrawal_tax_priority=WithdrawalTaxPriority.TAX_DEFERRED_TAXABLE_TAX_FREE,
            withdrawal_owner_priority=WithdrawalOwnerPriority.PRIMARY_FIRST,
            withdrawal_account_type_priority=WithdrawalAccountTypePriority.NO_PREFERENCE,
            withdrawal_allocation_method=WithdrawalAllocationMethod.DRAIN_ONE_THEN_NEXT,
            roth_handling_policy=RothHandlingPolicy.LAST_RESORT,
        ),
        people=[
            Person(
                person_id="p1",
                role=PersonRole.PRIMARY,
                display_name="Primary",
                birth_year=1965,
            ),
        ],
        buckets=[
            BucketDefinition(
                bucket_id="b3",
                bucket_name="Long-Term",
                bucket_type=BucketType.LONG_TERM,
            ),
        ],
        accounts=[
            Account(
                account_id="taxable-1",
                account_name="Brokerage",
                account_type=AccountType.TAXABLE_BROKERAGE,
                owner=AccountOwner.PRIMARY,
                tax_treatment=TaxTreatment.TAXABLE,
                opening_balance=Decimal("10000.00"),
                bucket_id="b3",
            ),
            Account(
                account_id="ira-1",
                account_name="IRA",
                account_type=AccountType.TRADITIONAL_IRA,
                owner=AccountOwner.PRIMARY,
                tax_treatment=TaxTreatment.TAX_DEFERRED,
                opening_balance=Decimal("15000.00"),
                bucket_id="b3",
            ),
        ],
    )

    result = generate_forecast(
        plan=plan,
        settings=ProjectionSettings(start_year=2026, number_of_years=1),
    )

    taxable_row = next(row for row in result.account_rows if row.account_id == "taxable-1")
    ira_row = next(row for row in result.account_rows if row.account_id == "ira-1")

    assert ira_row.auto_funding_withdrawals == Decimal("12000.00")
    assert taxable_row.auto_funding_withdrawals == Decimal("0.00")


def test_forecast_replenishes_bucket_chain_to_target_floor():
    plan = HouseholdPlan(
        plan_id="case-bucket-replenish",
        household_name="Bucket Replenishment Household",
        base_year=2026,
        settings=HouseholdSettings(
            auto_fund_shortfall=False,
            planned_annual_spending=Decimal("10.00"),
            default_bucket_expense_years=1.0,
            bucket_return_short_term=0.0,
            bucket_return_intermediate=0.0,
            bucket_return_long_term=0.0,
        ),
        people=[
            Person(
                person_id="p1",
                role=PersonRole.PRIMARY,
                display_name="Morgan",
                birth_year=1965,
            ),
        ],
        buckets=[
            BucketDefinition(
                bucket_id="b1",
                bucket_name="Short-Term",
                bucket_type=BucketType.SHORT_TERM,
                replenishment_source_bucket_id="b2",
            ),
            BucketDefinition(
                bucket_id="b2",
                bucket_name="Intermediate",
                bucket_type=BucketType.INTERMEDIATE,
                replenishment_source_bucket_id="b3",
            ),
            BucketDefinition(
                bucket_id="b3",
                bucket_name="Long-Term",
                bucket_type=BucketType.LONG_TERM,
            ),
        ],
        accounts=[
            Account(
                account_id="a1",
                account_name="Short Account",
                account_type=AccountType.CASH,
                owner=AccountOwner.PRIMARY,
                tax_treatment=TaxTreatment.TAXABLE,
                opening_balance=Decimal("0.00"),
                bucket_id="b1",
            ),
            Account(
                account_id="a2",
                account_name="Intermediate Account",
                account_type=AccountType.CD,
                owner=AccountOwner.PRIMARY,
                tax_treatment=TaxTreatment.TAXABLE,
                opening_balance=Decimal("10.00"),
                bucket_id="b2",
            ),
            Account(
                account_id="a3",
                account_name="Long Account",
                account_type=AccountType.TAXABLE_BROKERAGE,
                owner=AccountOwner.PRIMARY,
                tax_treatment=TaxTreatment.TAXABLE,
                opening_balance=Decimal("50.00"),
                bucket_id="b3",
            ),
        ],
    )

    result = generate_forecast(
        plan=plan,
        settings=ProjectionSettings(start_year=2026, number_of_years=1),
    )

    short_row = next(row for row in result.account_rows if row.account_id == "a1")
    intermediate_row = next(row for row in result.account_rows if row.account_id == "a2")
    long_row = next(row for row in result.account_rows if row.account_id == "a3")
    household_row = result.rows[0]

    assert short_row.replenishment_inflows == Decimal("10.00")
    assert short_row.end_balance == Decimal("10.00")
    assert intermediate_row.replenishment_outflows == Decimal("10.00")
    assert intermediate_row.replenishment_inflows == Decimal("10.00")
    assert intermediate_row.end_balance == Decimal("10.00")
    assert long_row.replenishment_outflows == Decimal("10.00")
    assert long_row.end_balance == Decimal("40.00")
    assert household_row.short_term_ending_assets == Decimal("10.00")
    assert household_row.intermediate_ending_assets == Decimal("10.00")
    assert household_row.long_term_ending_assets == Decimal("40.00")
    assert household_row.total_ending_assets == Decimal("60.00")


def test_export_plan_for_ui_writes_into_repo_exports_folder():
    plan = HouseholdPlan(
        plan_id="case-export-path",
        household_name="Export Household",
        base_year=2026,
        settings=HouseholdSettings(),
        people=[
            Person(
                person_id="p1",
                role=PersonRole.PRIMARY,
                display_name="Taylor",
                birth_year=1970,
            ),
        ],
    )

    path = Path(export_plan_for_ui(plan))

    try:
        assert path.name.startswith("case-export-path_")
        assert path.suffix == ".xlsx"
        assert path.parent.name == "exports"
        assert path.exists()
    finally:
        path.unlink(missing_ok=True)


def test_export_plan_for_ui_can_save_updated_copy_next_to_imported_workbook(tmp_path):
    plan = HouseholdPlan(
        plan_id="case-export-copy",
        household_name="Export Household",
        base_year=2026,
        settings=HouseholdSettings(),
        people=[
            Person(
                person_id="p1",
                role=PersonRole.PRIMARY,
                display_name="Taylor",
                birth_year=1970,
            ),
        ],
    )

    source_path = tmp_path / "my_case.xlsx"
    export_case_workbook(source_path, plan)

    path = Path(
        export_plan_for_ui(
            plan,
            export_mode=EXPORT_MODE_SAVE_UPDATED_COPY,
            imported_workbook_path=str(source_path),
            export_directory=str(tmp_path),
        )
    )

    try:
        assert path.parent == tmp_path
        assert path.name == "my_case_updated.xlsx"
        assert path.exists()
    finally:
        path.unlink(missing_ok=True)
        source_path.unlink(missing_ok=True)


def test_export_plan_for_ui_can_update_imported_workbook_in_place(tmp_path):
    plan = HouseholdPlan(
        plan_id="case-export-update",
        household_name="Export Household",
        base_year=2026,
        settings=HouseholdSettings(),
        people=[
            Person(
                person_id="p1",
                role=PersonRole.PRIMARY,
                display_name="Taylor",
                birth_year=1970,
            ),
        ],
    )

    source_path = tmp_path / "my_case.xlsx"
    export_case_workbook(source_path, plan)

    path = Path(
        export_plan_for_ui(
            plan,
            export_mode=EXPORT_MODE_UPDATE_IMPORTED_WORKBOOK,
            imported_workbook_path=str(source_path),
            export_directory=str(tmp_path / "out"),
        )
    )

    try:
        assert path == (tmp_path / "out" / "my_case.xlsx")
        assert path.exists()
    finally:
        path.unlink(missing_ok=True)
        source_path.unlink(missing_ok=True)


def test_export_preserves_imported_workbook_column_widths(tmp_path):
    plan = HouseholdPlan(
        plan_id="case-export-widths",
        household_name="Export Household",
        base_year=2026,
        settings=HouseholdSettings(),
        people=[
            Person(
                person_id="p1",
                role=PersonRole.PRIMARY,
                display_name="Taylor",
                birth_year=1970,
            ),
        ],
    )

    source_path = tmp_path / "source.xlsx"
    export_case_workbook(source_path, plan)

    from openpyxl import load_workbook

    source_workbook = load_workbook(source_path)
    source_workbook["Household"].column_dimensions["A"].width = 32
    source_workbook["Household"].column_dimensions["B"].width = 48
    source_workbook.save(source_path)

    updated_path = tmp_path / "widths_out.xlsx"
    export_case_workbook(
        updated_path,
        plan,
        template_path=source_path,
    )

    try:
        updated_workbook = load_workbook(updated_path)
        assert updated_workbook["Household"].column_dimensions["A"].width == 32
        assert updated_workbook["Household"].column_dimensions["B"].width == 48
    finally:
        updated_workbook.close()


def test_export_keeps_existing_accounts_sheet_and_inserts_new_forecast_tabs_first(
    tmp_path,
    monkeypatch,
):
    plan = sample_plan()
    source_path = tmp_path / "source.xlsx"
    export_case_workbook(source_path, plan)

    from openpyxl import load_workbook

    source_workbook = load_workbook(source_path)
    source_workbook["Accounts"]["B2"] = "User Edited IRA"
    source_workbook.create_sheet("Forecast-Amts-21-Oct-26-235959")
    source_workbook.create_sheet("Forecast-Accts-21-Oct-26-235959")
    source_workbook.save(source_path)

    monkeypatch.setattr(
        workbook_io,
        "_forecast_timestamp_label",
        lambda: "22-Oct-26-114533",
    )

    forecast = generate_forecast(
        plan,
        ProjectionSettings(start_year=plan.base_year, number_of_years=1),
    )

    updated_path = tmp_path / "forecast_out.xlsx"
    export_case_workbook(
        updated_path,
        plan,
        forecast=forecast,
        template_path=source_path,
    )

    updated_workbook = load_workbook(updated_path)

    try:
        assert updated_workbook["Accounts"]["B2"].value == "User Edited IRA"
        assert "Forecast-Sumry-22-Oct-26-114533" in updated_workbook.sheetnames
        assert "Forecast-Amts-22-Oct-26-114533" in updated_workbook.sheetnames
        assert "Forecast-Accts-22-Oct-26-114533" in updated_workbook.sheetnames
        assert "Forecast-Amts-21-Oct-26-235959" in updated_workbook.sheetnames
        assert "Forecast-Accts-21-Oct-26-235959" in updated_workbook.sheetnames
        assert (
            updated_workbook.sheetnames.index("Forecast-Sumry-22-Oct-26-114533")
            < updated_workbook.sheetnames.index("Forecast-Amts-21-Oct-26-235959")
        )
        assert (
            updated_workbook.sheetnames.index("Forecast-Amts-22-Oct-26-114533")
            < updated_workbook.sheetnames.index("Forecast-Amts-21-Oct-26-235959")
        )
        assert (
            updated_workbook.sheetnames.index("Forecast-Accts-22-Oct-26-114533")
            < updated_workbook.sheetnames.index("Forecast-Accts-21-Oct-26-235959")
        )
        assert (
            updated_workbook.sheetnames.index("Forecast-Amts-22-Oct-26-114533")
            > updated_workbook.sheetnames.index("Actual Balances")
        )
        amounts_sheet = updated_workbook["Forecast-Amts-22-Oct-26-114533"]
        assert amounts_sheet["A2"].value == forecast.rows[0].year
        assert amounts_sheet["A2"].number_format == workbook_io.YEAR_NUMBER_FORMAT
        assert amounts_sheet["B2"].value == workbook_io._round_amount_for_export(
            forecast.rows[0].explicit_income_total
        )
        assert amounts_sheet["B2"].number_format == workbook_io.CURRENCY_NUMBER_FORMAT
        accounts_sheet = updated_workbook["Forecast-Accts-22-Oct-26-114533"]
        assert accounts_sheet["A2"].value == forecast.account_rows[0].year
        assert accounts_sheet["A2"].number_format == workbook_io.YEAR_NUMBER_FORMAT
        assert accounts_sheet["E2"].value == forecast.account_rows[0].effective_annual_return_rate
        assert accounts_sheet["E2"].number_format == workbook_io.PERCENT_NUMBER_FORMAT
        assert accounts_sheet["F2"].value == workbook_io._round_amount_for_export(
            forecast.account_rows[0].start_balance
        )
        assert accounts_sheet["F2"].number_format == workbook_io.CURRENCY_NUMBER_FORMAT
    finally:
        updated_workbook.close()


def test_export_adds_timestamped_monte_carlo_sheet(tmp_path, monkeypatch):
    plan = sample_plan()
    plan.settings.return_model_type = ReturnModelType.MONTE_CARLO
    plan.settings.monte_carlo_simulations = 5
    plan.settings.monte_carlo_seed = 7

    source_path = tmp_path / "source_mc.xlsx"
    export_case_workbook(source_path, sample_plan())

    monkeypatch.setattr(
        workbook_io,
        "_forecast_timestamp_label",
        lambda: "22-Oct-26-114533",
    )

    forecast = generate_forecast(
        plan,
        ProjectionSettings(start_year=plan.base_year, number_of_years=1),
    )

    updated_path = tmp_path / "forecast_mc_out.xlsx"
    export_case_workbook(
        updated_path,
        plan,
        forecast=forecast,
        template_path=source_path,
    )

    from openpyxl import load_workbook

    updated_workbook = load_workbook(updated_path)

    try:
        assert "Forecast-Sumry-22-Oct-26-114533" in updated_workbook.sheetnames
        assert "Forecast-Amts-22-Oct-26-114533" in updated_workbook.sheetnames
        assert "Forecast-Accts-22-Oct-26-114533" in updated_workbook.sheetnames
        assert "Forecast-MC-22-Oct-26-114533" in updated_workbook.sheetnames
    finally:
        updated_workbook.close()


def test_export_adds_headline_summary_lines_to_forecast_summary_sheet(tmp_path, monkeypatch):
    plan = sample_plan("3-Bucket Sample")
    source_path = tmp_path / "source_summary.xlsx"
    export_case_workbook(source_path, plan)

    monkeypatch.setattr(
        workbook_io,
        "_forecast_timestamp_label",
        lambda: "22-Oct-26-114533",
    )

    forecast = generate_forecast(
        plan,
        ProjectionSettings(start_year=plan.base_year, number_of_years=5),
    )

    updated_path = tmp_path / "forecast_summary_out.xlsx"
    export_case_workbook(
        updated_path,
        plan,
        forecast=forecast,
        template_path=source_path,
    )

    from openpyxl import load_workbook

    updated_workbook = load_workbook(updated_path)

    try:
        sheet = updated_workbook["Forecast-Sumry-22-Oct-26-114533"]
        headline_lines = workbook_io._build_headline_summary_blob(plan, forecast).splitlines()
        warning_lines = workbook_io._build_warnings_blob(plan, forecast).splitlines()
        preview_headers, preview_rows = workbook_io._build_next_five_years_preview(plan, forecast)
        action_headers, action_rows = workbook_io._build_recommended_actions(plan, forecast)
        assumptions_lines = workbook_io._build_key_assumptions_blob(plan).splitlines()
        metadata_lines = workbook_io._build_run_metadata_blob(
            plan=plan,
            forecast=forecast,
            generated_on="22-Oct-26-114533",
            source_workbook_name=source_path.name,
        ).splitlines()
        warning_start_row = len(headline_lines) + 2
        preview_start_row = warning_start_row + len(warning_lines) + 1
        actions_start_row = preview_start_row + len(preview_rows) + 2
        assumptions_start_row = actions_start_row + len(action_rows) + 2
        metadata_start_row = assumptions_start_row + len(assumptions_lines) + 1
        assert sheet.freeze_panes is None
        assert sheet["A1"].value == "Forecast Headline Summary"
        assert sheet["A1"].alignment.wrap_text is True
        assert sheet["A1"].font.bold is True
        assert sheet.column_dimensions["A"].width == 32
        assert sheet["B1"].value is not None
        assert sheet["B1"].value.startswith("Starting Assets:")
        assert sheet["B2"].value is not None
        assert sheet["B2"].value.startswith("Projected Ending Assets:")
        assert sheet["B3"].value is not None
        assert sheet["B3"].value.startswith("Assets Last Through Final Year:")
        assert sheet.cell(warning_start_row - 1, 1).value is None
        assert sheet.cell(warning_start_row - 1, 2).value is None
        assert sheet.cell(warning_start_row, 1).value == "Key Warnings / Observations"
        assert sheet.cell(warning_start_row, 1).alignment.wrap_text is True
        assert sheet.cell(warning_start_row, 1).font.bold is True
        assert warning_lines
        assert sheet.cell(warning_start_row, 2).value == warning_lines[0]
        assert sheet.cell(preview_start_row, 1).value == "Next 5 Years Preview"
        assert sheet.cell(preview_start_row, 1).font.bold is True
        assert [
            sheet.cell(preview_start_row, column_index).value
            for column_index in range(2, 2 + len(preview_headers))
        ] == preview_headers
        assert all(
            sheet.cell(preview_start_row, column_index).font.bold is True
            for column_index in range(2, 2 + len(preview_headers))
        )
        assert preview_rows
        assert sheet.cell(preview_start_row + 1, 2).value == preview_rows[0][0]
        assert sheet.cell(preview_start_row + 1, 3).value == preview_rows[0][1]
        assert sheet.cell(preview_start_row + 1, 10).value == preview_rows[0][8]
        assert sheet.cell(preview_start_row + 1, 11).value == preview_rows[0][9]
        assert isinstance(sheet.cell(preview_start_row + 1, 3).value, int)
        assert sheet.cell(preview_start_row + 1, 2).number_format == workbook_io.YEAR_NUMBER_FORMAT
        assert sheet.cell(preview_start_row + 1, 3).number_format == workbook_io.CURRENCY_NUMBER_FORMAT
        assert sheet.cell(preview_start_row + 1, 11).number_format == workbook_io.CURRENCY_NUMBER_FORMAT
        assert sheet.cell(actions_start_row, 1).value == "Recommended Actions"
        assert sheet.cell(actions_start_row, 1).font.bold is True
        assert [
            sheet.cell(actions_start_row, column_index).value
            for column_index in range(2, 2 + len(action_headers))
        ] == action_headers
        assert action_rows
        assert sheet.cell(actions_start_row + 1, 2).value == action_rows[0][0]
        assert sheet.cell(actions_start_row + 1, 3).value == action_rows[0][1]
        assert sheet.cell(actions_start_row + 1, 4).value == action_rows[0][2]
        assert sheet.cell(assumptions_start_row, 1).value == "Key Assumptions"
        assert sheet.cell(assumptions_start_row, 1).font.bold is True
        assert assumptions_lines
        assert sheet.cell(assumptions_start_row, 2).value == assumptions_lines[0]
        assert sheet.cell(metadata_start_row, 1).value == "Run Metadata"
        assert sheet.cell(metadata_start_row, 1).font.bold is True
        assert metadata_lines
        assert sheet.cell(metadata_start_row, 2).value == metadata_lines[0]
        assert len(sheet._charts) == 0
    finally:
        updated_workbook.close()


def test_forecast_report_markdown_and_pdf_generation(tmp_path):
    plan = sample_plan("3-Bucket Sample")
    forecast = generate_forecast(
        plan,
        ProjectionSettings(start_year=plan.base_year, number_of_years=5),
    )

    report = build_forecast_report(
        plan,
        forecast,
        generated_on="23-Oct-2026 10:15:30 AM",
        source_workbook_name="sample.xlsx",
    )
    markdown = render_report_markdown(report)
    _, generated_markdown, pdf_path = generate_report_assets(
        plan,
        forecast,
        source_workbook_name="sample.xlsx",
        output_directory=tmp_path,
    )

    assert "# Retirement Forecast Report" in markdown
    assert "## 1. Executive Summary" in markdown
    assert "## 5. Recommended Actions" in markdown
    assert "| Year | Income | Withdrawals | Expenses | Taxes | RMD | Short-Term | Intermediate-Term | Long-Term | End Assets |" in markdown
    assert "Planning projection only." in markdown
    assert generated_markdown.startswith("# Retirement Forecast Report")
    assert Path(pdf_path).exists()
    assert Path(pdf_path).suffix == ".pdf"
    assert Path(pdf_path).stat().st_size > 0


def test_build_ui_instantiates_with_report_popup():
    demo = app_module.build_ui()
    assert demo is not None
