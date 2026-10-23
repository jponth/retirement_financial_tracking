from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.chart import Reference, ScatterChart, Series
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter

from retirement_financial_tracking.config import load_recommended_actions_config
from retirement_financial_tracking.domain.models import (
    Account,
    AccountOwner,
    AccountType,
    ActualBalanceSnapshot,
    BucketDefinition,
    BucketType,
    CashFlowCategory,
    FilingStatus,
    ForecastResult,
    HouseholdForecastRow,
    HouseholdPlan,
    HouseholdSettings,
    Holding,
    Person,
    PersonRole,
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
    sum_money,
)


YEAR_NUMBER_FORMAT = "0"
CURRENCY_NUMBER_FORMAT = "$#,##0"
PERCENT_NUMBER_FORMAT = "0.00%"


def export_case_workbook(
    path: str | Path,
    plan: HouseholdPlan,
    forecast: ForecastResult | None = None,
    template_path: str | Path | None = None,
) -> Path:
    workbook = _create_export_workbook(template_path)
    _write_household_sheet(workbook, plan)
    _write_people_sheet(workbook, plan)
    _write_buckets_sheet(workbook, plan)
    if "Accounts" not in workbook.sheetnames:
        _write_accounts_sheet(workbook, plan)
    _write_holdings_sheet(workbook, plan)
    _write_cash_flows_sheet(workbook, plan)
    _write_actual_balances_sheet(workbook, plan)
    if forecast is not None:
        timestamp_label = _forecast_timestamp_label()
        insertion_index = _forecast_insertion_index(workbook)
        _write_forecast_summary_sheet(
            workbook,
            plan,
            forecast,
            sheet_title=_next_available_output_title(
                workbook,
                f"Forecast-Sumry-{timestamp_label}",
            ),
            index=insertion_index,
            generated_on=timestamp_label,
            source_workbook_name=Path(template_path).name if template_path else "",
        )
        insertion_index += 1
        _write_forecast_sheet(
            workbook,
            forecast,
            sheet_title=_next_available_output_title(
                workbook,
                f"Forecast-Amts-{timestamp_label}",
            ),
            index=insertion_index,
        )
        insertion_index += 1
        _write_account_forecast_sheet(
            workbook,
            forecast,
            sheet_title=_next_available_output_title(
                workbook,
                f"Forecast-Accts-{timestamp_label}",
            ),
            index=insertion_index,
        )
        insertion_index += 1
        if forecast.return_model_type is ReturnModelType.MONTE_CARLO:
            _write_monte_carlo_summary_sheet(
                workbook,
                forecast,
                sheet_title=_next_available_output_title(
                    workbook,
                    f"Forecast-MC-{timestamp_label}",
                ),
                index=insertion_index,
            )
    destination = Path(path)
    workbook.save(destination)
    return destination


def _create_export_workbook(template_path: str | Path | None) -> Workbook:
    if template_path:
        template = Path(template_path)
        if template.exists():
            return load_workbook(template)
    return Workbook()


def import_case_workbook(path: str | Path) -> HouseholdPlan:
    workbook = load_workbook(Path(path), data_only=True)
    household_sheet = workbook["Household"]
    people_sheet = workbook["People"]
    buckets_sheet = workbook["Buckets"]
    accounts_sheet = workbook["Accounts"]
    holdings_sheet = workbook["Holdings"]
    cash_flows_sheet = workbook["Cash Flows"]
    actual_balances_sheet = workbook["Actual Balances"]

    household_data = _read_key_value_sheet(household_sheet)
    settings = HouseholdSettings(
        state=str(household_data.get("state") or "CT"),
        filing_status=FilingStatus(
            str(household_data.get("filing_status") or FilingStatus.MARRIED_FILING_JOINTLY.value)
        ),
        tax_model=TaxModelType(
            str(household_data.get("tax_model") or TaxModelType.EFFECTIVE_RATE.value)
        ),
        tax_projection_mode=TaxProjectionMode(
            str(
                household_data.get("tax_projection_mode")
                or TaxProjectionMode.STATIC.value
            )
        ),
        projection_years=int(household_data.get("projection_years") or 30),
        inflation_rate=float(household_data.get("inflation_rate") or 0.03),
        default_bucket_expense_years=float(
            household_data.get("default_bucket_expense_years") or 3.0
        ),
        return_model_type=ReturnModelType(
            str(household_data.get("return_model_type") or ReturnModelType.SIMPLE.value)
        ),
        return_scenario_type=ReturnScenarioType(
            str(household_data.get("return_scenario_type") or ReturnScenarioType.BASE.value)
        ),
        monte_carlo_simulations=int(household_data.get("monte_carlo_simulations") or 250),
        monte_carlo_seed=_to_int(household_data.get("monte_carlo_seed")),
        monte_carlo_depletion_target_year=_to_int(
            household_data.get("monte_carlo_depletion_target_year")
        ),
        monte_carlo_depletion_target_age=_to_int(
            household_data.get("monte_carlo_depletion_target_age")
        ),
        bucket_return_short_term=float(household_data.get("bucket_return_short_term") or 0.02),
        bucket_return_intermediate=float(
            household_data.get("bucket_return_intermediate") or 0.04
        ),
        bucket_return_long_term=float(household_data.get("bucket_return_long_term") or 0.06),
        bucket_return_other=float(household_data.get("bucket_return_other") or 0.03),
        bucket_volatility_short_term=float(
            household_data.get("bucket_volatility_short_term") or 0.01
        ),
        bucket_volatility_intermediate=float(
            household_data.get("bucket_volatility_intermediate") or 0.06
        ),
        bucket_volatility_long_term=float(
            household_data.get("bucket_volatility_long_term") or 0.12
        ),
        bucket_volatility_other=float(household_data.get("bucket_volatility_other") or 0.08),
        planned_annual_spending=_to_decimal(household_data.get("planned_annual_spending")),
        target_cash_reserve=_to_decimal(household_data.get("target_cash_reserve")),
        federal_effective_tax_rate=float(household_data.get("federal_effective_tax_rate") or 0.0),
        state_effective_tax_rate=float(household_data.get("state_effective_tax_rate") or 0.0),
        rmd_start_age=int(household_data.get("rmd_start_age") or 73),
        auto_fund_shortfall=_to_bool(household_data.get("auto_fund_shortfall"), default=True),
        use_withdrawal_priority_policy=_to_bool(
            household_data.get("use_withdrawal_priority_policy"),
            default=True,
        ),
        withdrawal_tax_priority=WithdrawalTaxPriority(
            str(
                household_data.get("withdrawal_tax_priority")
                or WithdrawalTaxPriority.TAXABLE_TAX_DEFERRED_TAX_FREE.value
            )
        ),
        withdrawal_owner_priority=WithdrawalOwnerPriority(
            str(
                household_data.get("withdrawal_owner_priority")
                or WithdrawalOwnerPriority.OLDER_FIRST.value
            )
        ),
        withdrawal_account_type_priority=WithdrawalAccountTypePriority(
            str(
                household_data.get("withdrawal_account_type_priority")
                or WithdrawalAccountTypePriority.NO_PREFERENCE.value
            )
        ),
        withdrawal_allocation_method=WithdrawalAllocationMethod(
            str(
                household_data.get("withdrawal_allocation_method")
                or WithdrawalAllocationMethod.DRAIN_ONE_THEN_NEXT.value
            )
        ),
        roth_handling_policy=RothHandlingPolicy(
            str(
                household_data.get("roth_handling_policy")
                or RothHandlingPolicy.LAST_RESORT.value
            )
        ),
        hsa_contribution_limit_self=_to_decimal(household_data.get("hsa_contribution_limit_self") or 4300),
        hsa_contribution_limit_family=_to_decimal(household_data.get("hsa_contribution_limit_family") or 8550),
        hsa_catch_up_amount=_to_decimal(household_data.get("hsa_catch_up_amount") or 1000),
        notes=str(household_data.get("notes") or ""),
    )
    people = [
        Person(
            person_id=str(row["person_id"]),
            role=PersonRole(
                str(row.get("role") or PersonRole.PRIMARY.value)
            ),
            display_name=str(row["display_name"]),
            birth_year=int(row["birth_year"]),
            retirement_year=_to_int(row.get("retirement_year")),
            life_expectancy=_to_int(row.get("life_expectancy")),
            social_security_claim_age=_to_float(row.get("social_security_claim_age")),
            estimated_monthly_social_security=_to_decimal(
                row.get("estimated_monthly_social_security")
            ),
            pension_start_age=_to_float(row.get("pension_start_age")),
            estimated_monthly_pension=_to_decimal(row.get("estimated_monthly_pension")),
            pension_indexed=_to_bool(row.get("pension_indexed")),
            medicare_start_year=_to_int(row.get("medicare_start_year")),
            annual_healthcare_premium=_to_decimal(row.get("annual_healthcare_premium")),
            annual_healthcare_out_of_pocket=_to_decimal(
                row.get("annual_healthcare_out_of_pocket")
            ),
            hsa_eligible=_to_bool(row.get("hsa_eligible")),
            desired_annual_hsa_contribution=_to_decimal(
                row.get("desired_annual_hsa_contribution")
            ),
        )
        for row in _read_table_rows(people_sheet)
        if row.get("person_id") not in (None, "")
    ]
    buckets = [
        BucketDefinition(
            bucket_id=str(row["bucket_id"]),
            bucket_name=str(row["bucket_name"]),
            bucket_type=BucketType(str(row["bucket_type"])),
            target_amount=_to_decimal(row.get("target_amount")),
            target_years=_to_float(row.get("target_years")),
            replenishment_source_bucket_id=_to_optional_str(
                row.get("replenishment_source_bucket_id")
            ),
            notes=str(row.get("notes") or ""),
        )
        for row in _read_table_rows(buckets_sheet)
        if row.get("bucket_id") not in (None, "")
    ]
    accounts = [
        Account(
            account_id=str(row["account_id"]),
            account_name=str(row["account_name"]),
            account_type=AccountType(
                str(row.get("account_type") or AccountType.OTHER.value)
            ),
            owner=AccountOwner(str(row["owner"])),
            custodian=str(row.get("custodian") or ""),
            tax_treatment=TaxTreatment(str(row["tax_treatment"])),
            opening_balance=_to_decimal(row.get("opening_balance")),
            expected_annual_return_rate=float(row.get("expected_annual_return_rate") or 0.0),
            bucket_id=_to_optional_str(row.get("bucket_id")),
            contribution_allowed=_to_bool(row.get("contribution_allowed"), default=True),
            withdrawal_allowed=_to_bool(row.get("withdrawal_allowed"), default=True),
            roth_conversion_source_allowed=_to_bool(
                row.get("roth_conversion_source_allowed")
            ),
        )
        for row in _read_table_rows(accounts_sheet)
        if row.get("account_id") not in (None, "")
    ]
    holdings = [
        Holding(
            holding_id=str(row["holding_id"]),
            account_id=str(row["account_id"]),
            holding_name=str(row["holding_name"]),
            ticker=str(row.get("ticker") or ""),
            asset_class=str(row.get("asset_class") or ""),
            market_value=_to_decimal(row.get("market_value")),
            bucket_id=_to_optional_str(row.get("bucket_id")),
            maturity_year=_to_int(row.get("maturity_year")),
            fdic_issuer=str(row.get("fdic_issuer") or ""),
            notes=str(row.get("notes") or ""),
        )
        for row in _read_table_rows(holdings_sheet)
        if row.get("holding_id") not in (None, "")
    ]
    cash_flows = [
        RecurringCashFlow(
            flow_id=str(row["flow_id"]),
            flow_name=str(row["flow_name"]),
            category=CashFlowCategory(str(row["category"])),
            annual_amount=_to_decimal(row.get("annual_amount")),
            start_year=int(row["start_year"]),
            end_year=int(row["end_year"]),
            annual_growth_rate=float(row.get("annual_growth_rate") or 0.0),
            person_id=_to_optional_str(row.get("person_id")),
            target_account_id=_to_optional_str(row.get("target_account_id")),
            notes=str(row.get("notes") or ""),
        )
        for row in _read_table_rows(cash_flows_sheet)
        if row.get("flow_id") not in (None, "")
    ]
    actual_balance_snapshots = [
        ActualBalanceSnapshot(
            snapshot_id=str(row["snapshot_id"]),
            account_id=str(row["account_id"]),
            as_of_date=str(row["as_of_date"]),
            balance=_to_decimal(row.get("balance")),
            source=str(row.get("source") or ""),
        )
        for row in _read_table_rows(actual_balances_sheet)
        if row.get("snapshot_id") not in (None, "")
    ]
    return HouseholdPlan(
        plan_id=str(household_data["plan_id"]),
        household_name=str(household_data["household_name"]),
        base_year=int(household_data["base_year"]),
        settings=settings,
        people=people,
        buckets=buckets,
        accounts=accounts,
        holdings=holdings,
        cash_flows=cash_flows,
        actual_balance_snapshots=actual_balance_snapshots,
    )


def _write_household_sheet(workbook: Workbook, plan: HouseholdPlan) -> None:
    sheet = _get_or_create_sheet(workbook, "Household", make_active=True)
    _clear_sheet(sheet)
    sheet.append(["field", "value"])
    sheet.append(["plan_id", plan.plan_id])
    sheet.append(["household_name", plan.household_name])
    sheet.append(["base_year", plan.base_year])
    sheet.append(["state", plan.settings.state])
    sheet.append(["filing_status", plan.settings.filing_status.value])
    sheet.append(["tax_model", plan.settings.tax_model.value])
    sheet.append(["tax_projection_mode", plan.settings.tax_projection_mode.value])
    sheet.append(["projection_years", plan.settings.projection_years])
    sheet.append(["inflation_rate", plan.settings.inflation_rate])
    sheet.append(["default_bucket_expense_years", plan.settings.default_bucket_expense_years])
    sheet.append(["return_model_type", plan.settings.return_model_type.value])
    sheet.append(["return_scenario_type", plan.settings.return_scenario_type.value])
    sheet.append(["monte_carlo_simulations", plan.settings.monte_carlo_simulations])
    sheet.append(["monte_carlo_seed", plan.settings.monte_carlo_seed])
    sheet.append(["monte_carlo_depletion_target_year", plan.settings.monte_carlo_depletion_target_year])
    sheet.append(["monte_carlo_depletion_target_age", plan.settings.monte_carlo_depletion_target_age])
    sheet.append(["bucket_return_short_term", plan.settings.bucket_return_short_term])
    sheet.append(["bucket_return_intermediate", plan.settings.bucket_return_intermediate])
    sheet.append(["bucket_return_long_term", plan.settings.bucket_return_long_term])
    sheet.append(["bucket_return_other", plan.settings.bucket_return_other])
    sheet.append(["bucket_volatility_short_term", plan.settings.bucket_volatility_short_term])
    sheet.append(["bucket_volatility_intermediate", plan.settings.bucket_volatility_intermediate])
    sheet.append(["bucket_volatility_long_term", plan.settings.bucket_volatility_long_term])
    sheet.append(["bucket_volatility_other", plan.settings.bucket_volatility_other])
    sheet.append(["planned_annual_spending", float(plan.settings.planned_annual_spending)])
    sheet.append(["target_cash_reserve", float(plan.settings.target_cash_reserve)])
    sheet.append(["federal_effective_tax_rate", plan.settings.federal_effective_tax_rate])
    sheet.append(["state_effective_tax_rate", plan.settings.state_effective_tax_rate])
    sheet.append(["rmd_start_age", plan.settings.rmd_start_age])
    sheet.append(["auto_fund_shortfall", plan.settings.auto_fund_shortfall])
    sheet.append(["use_withdrawal_priority_policy", plan.settings.use_withdrawal_priority_policy])
    sheet.append(["withdrawal_tax_priority", plan.settings.withdrawal_tax_priority.value])
    sheet.append(["withdrawal_owner_priority", plan.settings.withdrawal_owner_priority.value])
    sheet.append([
        "withdrawal_account_type_priority",
        plan.settings.withdrawal_account_type_priority.value,
    ])
    sheet.append([
        "withdrawal_allocation_method",
        plan.settings.withdrawal_allocation_method.value,
    ])
    sheet.append(["roth_handling_policy", plan.settings.roth_handling_policy.value])
    sheet.append(["hsa_contribution_limit_self", float(plan.settings.hsa_contribution_limit_self)])
    sheet.append(["hsa_contribution_limit_family", float(plan.settings.hsa_contribution_limit_family)])
    sheet.append(["hsa_catch_up_amount", float(plan.settings.hsa_catch_up_amount)])
    sheet.append(["notes", plan.settings.notes])


def _write_people_sheet(workbook: Workbook, plan: HouseholdPlan) -> None:
    sheet = _get_or_create_sheet(workbook, "People")
    _clear_sheet(sheet)
    sheet.append(
        [
            "person_id",
            "role",
            "display_name",
            "birth_year",
            "retirement_year",
            "life_expectancy",
            "social_security_claim_age",
            "estimated_monthly_social_security",
            "pension_start_age",
            "estimated_monthly_pension",
            "pension_indexed",
            "medicare_start_year",
            "annual_healthcare_premium",
            "annual_healthcare_out_of_pocket",
            "hsa_eligible",
            "desired_annual_hsa_contribution",
        ]
    )
    for person in plan.people:
        sheet.append(
            [
                person.person_id,
                person.role.value,
                person.display_name,
                person.birth_year,
                person.retirement_year,
                person.life_expectancy,
                person.social_security_claim_age,
                float(person.estimated_monthly_social_security),
                person.pension_start_age,
                float(person.estimated_monthly_pension),
                person.pension_indexed,
                person.medicare_start_year,
                float(person.annual_healthcare_premium),
                float(person.annual_healthcare_out_of_pocket),
                person.hsa_eligible,
                float(person.desired_annual_hsa_contribution),
            ]
        )


def _write_buckets_sheet(workbook: Workbook, plan: HouseholdPlan) -> None:
    sheet = _get_or_create_sheet(workbook, "Buckets")
    _clear_sheet(sheet)
    sheet.append(
        [
            "bucket_id",
            "bucket_name",
            "bucket_type",
            "target_amount",
            "target_years",
            "replenishment_source_bucket_id",
            "notes",
        ]
    )
    for bucket in plan.buckets:
        sheet.append(
            [
                bucket.bucket_id,
                bucket.bucket_name,
                bucket.bucket_type.value,
                float(bucket.target_amount),
                bucket.target_years,
                bucket.replenishment_source_bucket_id or "",
                bucket.notes,
            ]
        )


def _write_accounts_sheet(workbook: Workbook, plan: HouseholdPlan) -> None:
    sheet = _get_or_create_sheet(workbook, "Accounts")
    _clear_sheet(sheet)
    sheet.append(
        [
            "account_id",
            "account_name",
            "account_type",
            "owner",
            "custodian",
            "tax_treatment",
            "opening_balance",
            "expected_annual_return_rate",
            "bucket_id",
            "contribution_allowed",
            "withdrawal_allowed",
            "roth_conversion_source_allowed",
        ]
    )
    for account in plan.accounts:
        sheet.append(
            [
                account.account_id,
                account.account_name,
                account.account_type.value,
                account.owner.value,
                account.custodian,
                account.tax_treatment.value,
                float(account.opening_balance),
                account.expected_annual_return_rate,
                account.bucket_id or "",
                account.contribution_allowed,
                account.withdrawal_allowed,
                account.roth_conversion_source_allowed,
            ]
        )


def _write_holdings_sheet(workbook: Workbook, plan: HouseholdPlan) -> None:
    sheet = _get_or_create_sheet(workbook, "Holdings")
    _clear_sheet(sheet)
    sheet.append(
        [
            "holding_id",
            "account_id",
            "holding_name",
            "ticker",
            "asset_class",
            "market_value",
            "bucket_id",
            "maturity_year",
            "fdic_issuer",
            "notes",
        ]
    )
    for holding in plan.holdings:
        sheet.append(
            [
                holding.holding_id,
                holding.account_id,
                holding.holding_name,
                holding.ticker,
                holding.asset_class,
                float(holding.market_value),
                holding.bucket_id or "",
                holding.maturity_year,
                holding.fdic_issuer,
                holding.notes,
            ]
        )


def _write_cash_flows_sheet(workbook: Workbook, plan: HouseholdPlan) -> None:
    sheet = _get_or_create_sheet(workbook, "Cash Flows")
    _clear_sheet(sheet)
    sheet.append(
        [
            "flow_id",
            "flow_name",
            "category",
            "annual_amount",
            "start_year",
            "end_year",
            "annual_growth_rate",
            "person_id",
            "target_account_id",
            "notes",
        ]
    )
    for flow in plan.cash_flows:
        sheet.append(
            [
                flow.flow_id,
                flow.flow_name,
                flow.category.value,
                float(flow.annual_amount),
                flow.start_year,
                flow.end_year,
                flow.annual_growth_rate,
                flow.person_id or "",
                flow.target_account_id or "",
                flow.notes,
            ]
        )


def _write_actual_balances_sheet(workbook: Workbook, plan: HouseholdPlan) -> None:
    sheet = _get_or_create_sheet(workbook, "Actual Balances")
    _clear_sheet(sheet)
    sheet.append(["snapshot_id", "account_id", "as_of_date", "balance", "source"])
    for snapshot in plan.actual_balance_snapshots:
        sheet.append(
            [
                snapshot.snapshot_id,
                snapshot.account_id,
                snapshot.as_of_date,
                float(snapshot.balance),
                snapshot.source,
            ]
        )


def _write_forecast_sheet(
    workbook: Workbook,
    forecast: ForecastResult,
    *,
    sheet_title: str,
    index: int,
) -> None:
    sheet = workbook.create_sheet(sheet_title, index=index)
    headers = [
        "year",
        "explicit_income_total",
        "social_security_total",
        "pension_total",
        "income_total",
        "living_expense_total",
        "healthcare_total",
        "hsa_contribution_total",
        "explicit_expense_total",
        "expense_total",
        "explicit_tax_total",
        "derived_tax_total",
        "tax_total",
        "contribution_total",
        "hsa_healthcare_withdrawal_total",
        "explicit_withdrawal_total",
        "rmd_withdrawal_total",
        "auto_funding_withdrawal_total",
        "withdrawal_total",
        "short_term_ending_assets",
        "intermediate_ending_assets",
        "long_term_ending_assets",
        "net_cash_flow",
        "total_starting_assets",
        "total_ending_assets",
    ]
    sheet.append(headers)
    for row in forecast.rows:
        _append_formatted_row(
            sheet,
            [
                row.year,
                _round_amount_for_export(row.explicit_income_total),
                _round_amount_for_export(row.social_security_total),
                _round_amount_for_export(row.pension_total),
                _round_amount_for_export(row.income_total),
                _round_amount_for_export(row.living_expense_total),
                _round_amount_for_export(row.healthcare_total),
                _round_amount_for_export(row.hsa_contribution_total),
                _round_amount_for_export(row.explicit_expense_total),
                _round_amount_for_export(row.expense_total),
                _round_amount_for_export(row.explicit_tax_total),
                _round_amount_for_export(row.derived_tax_total),
                _round_amount_for_export(row.tax_total),
                _round_amount_for_export(row.contribution_total),
                _round_amount_for_export(row.hsa_healthcare_withdrawal_total),
                _round_amount_for_export(row.explicit_withdrawal_total),
                _round_amount_for_export(row.rmd_withdrawal_total),
                _round_amount_for_export(row.auto_funding_withdrawal_total),
                _round_amount_for_export(row.withdrawal_total),
                _round_amount_for_export(row.short_term_ending_assets),
                _round_amount_for_export(row.intermediate_ending_assets),
                _round_amount_for_export(row.long_term_ending_assets),
                _round_amount_for_export(row.net_cash_flow),
                _round_amount_for_export(row.total_starting_assets),
                _round_amount_for_export(row.total_ending_assets),
            ],
            {
                1: YEAR_NUMBER_FORMAT,
                **{column_index: CURRENCY_NUMBER_FORMAT for column_index in range(2, len(headers) + 1)},
            },
        )


def _write_forecast_summary_sheet(
    workbook: Workbook,
    plan: HouseholdPlan,
    forecast: ForecastResult,
    *,
    sheet_title: str,
    index: int,
    generated_on: str,
    source_workbook_name: str,
) -> None:
    sheet = workbook.create_sheet(sheet_title, index=index)
    label_alignment = Alignment(wrap_text=True, vertical="top")
    label_font = Font(bold=True)
    sheet.column_dimensions["A"].width = 32
    headline_lines = _build_headline_summary_blob(plan, forecast).splitlines()
    warning_lines = _build_warnings_blob(plan, forecast).splitlines()
    preview_headers, preview_rows = _build_next_five_years_preview(plan, forecast)
    action_headers, action_rows = _build_recommended_actions(plan, forecast)
    assumptions_lines = _build_key_assumptions_blob(plan).splitlines()
    metadata_lines = _build_run_metadata_blob(
        plan=plan,
        forecast=forecast,
        generated_on=generated_on,
        source_workbook_name=source_workbook_name,
    ).splitlines()

    sheet["A1"] = "Forecast Headline Summary"
    sheet["A1"].alignment = label_alignment
    sheet["A1"].font = label_font
    for row_index, line in enumerate(headline_lines, start=1):
        sheet.cell(row_index, 2, line)

    warning_start_row = len(headline_lines) + 2
    sheet.cell(warning_start_row, 1, "Key Warnings / Observations")
    sheet.cell(warning_start_row, 1).alignment = label_alignment
    sheet.cell(warning_start_row, 1).font = label_font
    for row_index, line in enumerate(warning_lines, start=warning_start_row):
        sheet.cell(row_index, 2, line)

    preview_start_row = warning_start_row + len(warning_lines) + 1
    sheet.cell(preview_start_row, 1, "Next 5 Years Preview")
    sheet.cell(preview_start_row, 1).alignment = label_alignment
    sheet.cell(preview_start_row, 1).font = label_font
    for column_index, header in enumerate(preview_headers, start=2):
        sheet.cell(preview_start_row, column_index, header).font = label_font
    for row_offset, preview_row in enumerate(preview_rows, start=1):
        for column_index, value in enumerate(preview_row, start=2):
            cell = sheet.cell(preview_start_row + row_offset, column_index, value)
            cell.number_format = (
                YEAR_NUMBER_FORMAT if column_index == 2 else CURRENCY_NUMBER_FORMAT
            )

    actions_start_row = preview_start_row + len(preview_rows) + 2
    sheet.cell(actions_start_row, 1, "Recommended Actions")
    sheet.cell(actions_start_row, 1).alignment = label_alignment
    sheet.cell(actions_start_row, 1).font = label_font
    for column_index, header in enumerate(action_headers, start=2):
        sheet.cell(actions_start_row, column_index, header).font = label_font
    for row_offset, action_row in enumerate(action_rows, start=1):
        for column_index, value in enumerate(action_row, start=2):
            sheet.cell(actions_start_row + row_offset, column_index, value)

    assumptions_start_row = actions_start_row + len(action_rows) + 2
    sheet.cell(assumptions_start_row, 1, "Key Assumptions")
    sheet.cell(assumptions_start_row, 1).alignment = label_alignment
    sheet.cell(assumptions_start_row, 1).font = label_font
    for row_index, line in enumerate(assumptions_lines, start=assumptions_start_row):
        sheet.cell(row_index, 2, line)

    metadata_start_row = assumptions_start_row + len(assumptions_lines) + 1
    sheet.cell(metadata_start_row, 1, "Run Metadata")
    sheet.cell(metadata_start_row, 1).alignment = label_alignment
    sheet.cell(metadata_start_row, 1).font = label_font
    for row_index, line in enumerate(metadata_lines, start=metadata_start_row):
        sheet.cell(row_index, 2, line)


def _write_account_forecast_sheet(
    workbook: Workbook,
    forecast: ForecastResult,
    *,
    sheet_title: str,
    index: int,
) -> None:
    sheet = workbook.create_sheet(sheet_title, index=index)
    headers = [
        "year",
        "account_id",
        "account_name",
        "bucket_type",
        "effective_annual_return_rate",
        "start_balance",
        "contributions",
        "explicit_withdrawals",
        "rmd_withdrawals",
        "hsa_healthcare_withdrawals",
        "auto_funding_withdrawals",
        "replenishment_inflows",
        "replenishment_outflows",
        "withdrawals",
        "investment_growth",
        "end_balance",
    ]
    sheet.append(headers)
    for row in forecast.account_rows:
        _append_formatted_row(
            sheet,
            [
                row.year,
                row.account_id,
                row.account_name,
                row.bucket_type.value,
                row.effective_annual_return_rate,
                _round_amount_for_export(row.start_balance),
                _round_amount_for_export(row.contributions),
                _round_amount_for_export(row.explicit_withdrawals),
                _round_amount_for_export(row.rmd_withdrawals),
                _round_amount_for_export(row.hsa_healthcare_withdrawals),
                _round_amount_for_export(row.auto_funding_withdrawals),
                _round_amount_for_export(row.replenishment_inflows),
                _round_amount_for_export(row.replenishment_outflows),
                _round_amount_for_export(row.withdrawals),
                _round_amount_for_export(row.investment_growth),
                _round_amount_for_export(row.end_balance),
            ],
            {
                1: YEAR_NUMBER_FORMAT,
                5: PERCENT_NUMBER_FORMAT,
                **{column_index: CURRENCY_NUMBER_FORMAT for column_index in range(6, len(headers) + 1)},
            },
        )


def _write_monte_carlo_summary_sheet(
    workbook: Workbook,
    forecast: ForecastResult,
    *,
    sheet_title: str,
    index: int,
) -> None:
    if forecast.return_model_type is not ReturnModelType.MONTE_CARLO:
        return
    sheet = workbook.create_sheet(sheet_title, index=index)
    sheet.append(["field", "value"])
    sheet.append(["return_model_type", forecast.return_model_type.value])
    sheet.append(["monte_carlo_simulations", forecast.monte_carlo_simulations])
    sheet.append(["monte_carlo_seed", forecast.monte_carlo_seed])
    sheet.append(["final_total_assets_p10", float(forecast.final_total_assets_p10 or Decimal("0.00"))])
    sheet.append([
        "final_total_assets_median",
        float(forecast.final_total_assets_median or forecast.final_total_assets),
    ])
    sheet.append(["final_total_assets_p90", float(forecast.final_total_assets_p90 or Decimal("0.00"))])


def _read_key_value_sheet(sheet) -> dict[str, object]:
    return {str(row[0].value): row[1].value for row in sheet.iter_rows(min_row=2, max_col=2)}


def _forecast_timestamp_label() -> str:
    return datetime.now().strftime("%d-%b-%y-%H%M%S")


def _forecast_insertion_index(workbook: Workbook) -> int:
    output_indexes = [
        index
        for index, title in enumerate(workbook.sheetnames)
        if _is_forecast_output_sheet(title)
    ]
    if output_indexes:
        return min(output_indexes)
    if "Actual Balances" in workbook.sheetnames:
        return workbook.sheetnames.index("Actual Balances") + 1
    return len(workbook.sheetnames)


def _is_forecast_output_sheet(title: str) -> bool:
    return (
        title == "Forecast"
        or title == "Account Forecast"
        or title == "Monte Carlo Summary"
        or title.startswith("Forecast-Summary")
        or title.startswith("Forecast-Sumry-")
        or title.startswith("Forecast-Amts-")
        or title.startswith("Forecast-Accts-")
        or title.startswith("Forecast-MC-")
    )


def _next_available_output_title(workbook: Workbook, base_title: str) -> str:
    base_title = base_title[:31]
    if base_title not in workbook.sheetnames:
        return base_title
    counter = 2
    while True:
        suffix = f"-{counter}"
        candidate = f"{base_title[:31 - len(suffix)]}{suffix}"
        if candidate not in workbook.sheetnames:
            return candidate
        counter += 1


def _read_table_rows(sheet) -> list[dict[str, object]]:
    header_cells = next(sheet.iter_rows(min_row=1, max_row=1, values_only=True), ())
    headers = [str(value).strip() if value is not None else "" for value in header_cells]
    rows: list[dict[str, object]] = []
    for row_values in sheet.iter_rows(min_row=2, values_only=True):
        if not any(value not in (None, "") for value in row_values):
            continue
        row: dict[str, object] = {}
        for index, header in enumerate(headers):
            if not header:
                continue
            row[header] = row_values[index] if index < len(row_values) else None
        rows.append(row)
    return rows


def _get_or_create_sheet(workbook: Workbook, title: str, make_active: bool = False):
    if title in workbook.sheetnames:
        sheet = workbook[title]
    else:
        if make_active and workbook.sheetnames:
            sheet = workbook[workbook.sheetnames[0]]
            sheet.title = title
        else:
            sheet = workbook.create_sheet(title)
    if make_active:
        workbook.active = workbook.sheetnames.index(sheet.title)
    return sheet


def _clear_sheet(sheet) -> None:
    if sheet.max_row > 0:
        sheet.delete_rows(1, sheet.max_row)


def _to_decimal(value: object) -> Decimal:
    return Decimal(str(value or 0))


def _to_int(value: object) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


def _to_float(value: object) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def _to_optional_str(value: object) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _to_bool(value: object, default: bool = False) -> bool:
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    return text in {"1", "true", "yes", "y"}


def _write_summary_chart(sheet, forecast: ForecastResult) -> None:
    start_col = 6  # F
    start_row = 1
    headers = [
        "Year",
        "Income",
        "Withdrawal",
        "Expenses",
        "Taxes",
        "RMD",
        "End Assets",
        "Short-term",
    ]
    for offset, header in enumerate(headers):
        column = start_col + offset
        sheet.cell(start_row, column, header)
        sheet.column_dimensions[get_column_letter(column)].hidden = True

    for row_index, row in enumerate(forecast.rows, start=start_row + 1):
        values = [
            row.year,
            float(row.income_total),
            float(row.withdrawal_total),
            float(row.expense_total),
            float(row.tax_total),
            float(row.rmd_withdrawal_total),
            float(row.total_ending_assets),
            float(row.short_term_ending_assets),
        ]
        for offset, value in enumerate(values):
            sheet.cell(row_index, start_col + offset, value)

    if not forecast.rows:
        return

    chart = ScatterChart()
    chart.title = "Forecast Trend"
    chart.x_axis.title = "Year"
    chart.y_axis.title = "$"
    chart.x_axis.axPos = "b"
    chart.y_axis.axPos = "l"
    chart.x_axis.tickLblPos = "nextTo"
    chart.y_axis.tickLblPos = "nextTo"
    chart.x_axis.number_format = "0"
    chart.y_axis.number_format = "$#,##0"
    chart.height = 11
    chart.width = 20
    chart.style = 2
    chart.visible_cells_only = False
    chart.scatterStyle = "line"
    xvalues = Reference(
        sheet,
        min_col=start_col,
        max_col=start_col,
        min_row=start_row + 1,
        max_row=start_row + len(forecast.rows),
    )
    for series_col in range(start_col + 1, start_col + len(headers)):
        values = Reference(
            sheet,
            min_col=series_col,
            max_col=series_col,
            min_row=start_row + 1,
            max_row=start_row + len(forecast.rows),
        )
        title = Reference(
            sheet,
            min_col=series_col,
            max_col=series_col,
            min_row=start_row,
            max_row=start_row,
        )
        series = Series(values, xvalues, title_from_data=False, title=title)
        series.marker.symbol = "none"
        chart.series.append(series)
    sheet.add_chart(chart, "A3")


def _write_summary_blob(
    sheet,
    *,
    row: int,
    label: str,
    text: str,
    label_column: int,
    text_column: int,
    label_font: Font,
    wrapped_alignment: Alignment,
) -> None:
    sheet.cell(row, label_column, label).font = label_font
    sheet.cell(row, label_column).alignment = wrapped_alignment
    sheet.cell(row, text_column, text).alignment = wrapped_alignment
    line_count = max(3, text.count("\n") + 1)
    sheet.row_dimensions[row].height = max(42, line_count * 15)


def _write_table(
    sheet,
    *,
    start_row: int,
    headers: list[str],
    rows: list[list[object]],
    header_font: Font,
) -> None:
    for index, header in enumerate(headers, start=1):
        cell = sheet.cell(start_row, index, header)
        cell.font = header_font
        cell.alignment = Alignment(vertical="top")
    for row_offset, values in enumerate(rows, start=1):
        for column_index, value in enumerate(values, start=1):
            cell = sheet.cell(start_row + row_offset, column_index, value)
            cell.alignment = Alignment(vertical="top")


def _build_run_metadata_blob(
    *,
    plan: HouseholdPlan,
    forecast: ForecastResult,
    generated_on: str,
    source_workbook_name: str,
) -> str:
    lines = [
        f"Generated On: {generated_on}",
        f"Plan ID: {plan.plan_id}",
        f"Household Name: {plan.household_name}",
        f"Base Year: {plan.base_year}",
        f"Projection Years: {len(forecast.rows)}",
        f"Return Model: {plan.settings.return_model_type.value}",
        f"Tax Model: {plan.settings.tax_model.value}",
        f"Tax Projection Mode: {plan.settings.tax_projection_mode.value}",
    ]
    if source_workbook_name:
        lines.append(f"Workbook Source: {source_workbook_name}")
    return "\n".join(lines)


def _build_key_assumptions_blob(plan: HouseholdPlan) -> str:
    lines = [
        f"Planned Annual Spending: {_format_money(plan.settings.planned_annual_spending)}",
        f"Inflation Rate: {_format_percent(plan.settings.inflation_rate)}",
        f"Federal Tax Handling: {plan.settings.tax_model.value}",
        f"State: {plan.settings.state}",
        f"RMD Start Age: {plan.settings.rmd_start_age}",
        f"Auto Fund Shortfall: {_format_yes_no(plan.settings.auto_fund_shortfall)}",
        f"Withdrawal Tax Priority: {plan.settings.withdrawal_tax_priority.value}",
        f"Withdrawal Owner Priority: {plan.settings.withdrawal_owner_priority.value}",
        f"Withdrawal Allocation Method: {plan.settings.withdrawal_allocation_method.value}",
        f"Bucket Expense Years: {plan.settings.default_bucket_expense_years}",
    ]
    if plan.settings.return_model_type is ReturnModelType.SCENARIO_BASED:
        lines.append(f"Return Scenario: {plan.settings.return_scenario_type.value}")
    if plan.settings.return_model_type is ReturnModelType.MONTE_CARLO:
        lines.append(
            f"Monte Carlo Simulations: {plan.settings.monte_carlo_simulations:,}"
        )
        lines.append(
            "Monte Carlo Seed: "
            + (
                str(plan.settings.monte_carlo_seed)
                if plan.settings.monte_carlo_seed is not None
                else "random"
            )
        )
    return "\n".join(lines)


def _build_headline_summary_blob(plan: HouseholdPlan, forecast: ForecastResult) -> str:
    if not forecast.rows:
        return "No forecast rows were generated."
    first_row = forecast.rows[0]
    final_row = forecast.rows[-1]
    depletion_year = _forecast_depletion_year(forecast.rows)
    lines = [
        f"Starting Assets: {_format_money(first_row.total_starting_assets)}",
        f"Projected Ending Assets: {_format_money(forecast.final_total_assets)}",
        "Assets Last Through Final Year: "
        + _format_yes_no(depletion_year is None),
        f"Projection Horizon Ends: {final_row.year}",
        "Projected Depletion Year: "
        + (str(depletion_year) if depletion_year is not None else "None"),
        f"Final Year Total Tax: {_format_money(final_row.tax_total)}",
        f"Total Projected Withdrawals: {_format_money(sum_money(row.withdrawal_total for row in forecast.rows))}",
        f"Total Projected RMD Withdrawals: {_format_money(sum_money(row.rmd_withdrawal_total for row in forecast.rows))}",
        f"Total Projected HSA Contributions: {_format_money(sum_money(row.hsa_contribution_total for row in forecast.rows))}",
        "Total Projected HSA Healthcare Withdrawals: "
        + _format_money(sum_money(row.hsa_healthcare_withdrawal_total for row in forecast.rows)),
    ]
    if plan.settings.return_model_type is ReturnModelType.MONTE_CARLO:
        lines.extend(
            [
                f"Monte Carlo Final Assets P10: {_format_money(forecast.final_total_assets_p10 or Decimal('0.00'))}",
                f"Monte Carlo Final Assets Median: {_format_money(forecast.final_total_assets_median or forecast.final_total_assets)}",
                f"Monte Carlo Final Assets P90: {_format_money(forecast.final_total_assets_p90 or Decimal('0.00'))}",
            ]
        )
        target_year = plan.settings.monte_carlo_depletion_target_year
        if target_year is not None:
            lines.append(
                "Probability of Depletion by Target Year: "
                + _format_percent(
                    _depletion_probability_by_year(
                        forecast.monte_carlo_trial_depletion_years,
                        target_year,
                    )
                )
            )
    return "\n".join(lines)


def _build_warnings_blob(plan: HouseholdPlan, forecast: ForecastResult) -> str:
    warnings: list[str] = []
    depletion_year = _forecast_depletion_year(forecast.rows)
    if depletion_year is None and forecast.rows:
        warnings.append("Assets are projected to last through the full forecast horizon.")
    elif depletion_year is not None:
        warnings.append(f"Assets are projected to deplete in {depletion_year}.")

    for bucket in plan.buckets:
        shortfall_year = _bucket_shortfall_year(plan, forecast, bucket.bucket_id)
        if shortfall_year is not None:
            warnings.append(
                f"{bucket.bucket_name} is projected below its target floor in {shortfall_year}."
            )

    first_rmd_year = next(
        (row.year for row in forecast.rows if row.rmd_withdrawal_total > 0),
        None,
    )
    if first_rmd_year is not None:
        warnings.append(f"RMD withdrawals begin in {first_rmd_year} under the current assumptions.")

    if forecast.rows and forecast.rows[-1].tax_total > forecast.rows[0].tax_total * Decimal("1.25"):
        warnings.append("Projected taxes increase materially over the forecast horizon.")

    if (
        plan.settings.return_model_type is ReturnModelType.MONTE_CARLO
        and forecast.final_total_assets_p10 is not None
        and forecast.final_total_assets_median is not None
        and forecast.final_total_assets_p10 < forecast.final_total_assets_median * Decimal("0.75")
    ):
        warnings.append("Monte Carlo downside shows a meaningfully weaker ending-asset buffer.")

    warnings.append(
        "Forecast results are planning estimates and depend on current assumptions, tax tables, and actual balance updates."
    )
    return "\n".join(f"- {warning}" for warning in warnings)


def _build_next_five_years_preview(
    plan: HouseholdPlan,
    forecast: ForecastResult,
) -> tuple[list[str], list[list[object]]]:
    bucket_types_by_id = {bucket.bucket_id: bucket.bucket_type for bucket in plan.buckets}
    balances_by_year = _bucket_balances_by_year(plan, forecast)
    headers = [
        "Year",
        "Income",
        "Withdrawals",
        "Expenses",
        "Taxes",
        "RMD",
        "Short-Term",
        "Intermediate-Term",
        "Long-Term",
        "End Assets",
    ]
    rows: list[list[object]] = []
    for row in forecast.rows[:5]:
        bucket_balances = balances_by_year.get(row.year, {})
        short_term_balance = Decimal("0.00")
        intermediate_balance = Decimal("0.00")
        long_term_balance = Decimal("0.00")
        for bucket_id, balance in bucket_balances.items():
            bucket_type = bucket_types_by_id.get(bucket_id)
            if bucket_type is BucketType.SHORT_TERM:
                short_term_balance += balance
            elif bucket_type is BucketType.INTERMEDIATE:
                intermediate_balance += balance
            elif bucket_type is BucketType.LONG_TERM:
                long_term_balance += balance
        rows.append(
            [
                row.year,
                _round_amount_for_preview(row.income_total),
                _round_amount_for_preview(row.withdrawal_total),
                _round_amount_for_preview(row.expense_total),
                _round_amount_for_preview(row.tax_total),
                _round_amount_for_preview(row.rmd_withdrawal_total),
                _round_amount_for_preview(short_term_balance),
                _round_amount_for_preview(intermediate_balance),
                _round_amount_for_preview(long_term_balance),
                _round_amount_for_preview(row.total_ending_assets),
            ]
        )
    return headers, rows


def _build_recommended_actions(
    plan: HouseholdPlan,
    forecast: ForecastResult,
) -> tuple[list[str], list[list[object]]]:
    config = load_recommended_actions_config()
    headers = ["Timing", "Priority", "Action"]
    actions: list[list[object]] = []

    has_hsa = any(
        account.account_type is AccountType.HSA or account.tax_treatment is TaxTreatment.HSA
        for account in plan.accounts
    ) or any(person.hsa_eligible for person in plan.people)

    for action in config.recurring_actions:
        if action.condition == "has_hsa" and not has_hsa:
            continue
        actions.append([action.timing, action.priority, action.action])

    triggered_actions = config.triggered_actions

    for bucket in plan.buckets:
        shortfall_year = _bucket_shortfall_year(plan, forecast, bucket.bucket_id)
        if shortfall_year is not None:
            action = triggered_actions.get("bucket_shortfall")
            if action is not None:
                actions.append(
                    [
                        action.timing,
                        action.priority,
                        action.action_template.format(bucket_name=bucket.bucket_name),
                    ]
                )

    for person in plan.people:
        if person.retirement_year is None:
            continue
        start_year = forecast.rows[0].year if forecast.rows else plan.base_year
        end_year = forecast.rows[-1].year if forecast.rows else start_year
        if start_year <= person.retirement_year <= end_year:
            action = triggered_actions.get("retirement_transition")
            if action is not None:
                actions.append(
                    [
                        action.timing,
                        action.priority,
                        action.action_template.format(person_name=person.display_name),
                    ]
                )

    first_rmd_year = next(
        (row.year for row in forecast.rows if row.rmd_withdrawal_total > 0),
        None,
    )
    if first_rmd_year is not None:
        action = triggered_actions.get("first_rmd")
        if action is not None:
            actions.append([action.timing, action.priority, action.action_template])

    depletion_year = _forecast_depletion_year(forecast.rows)
    if depletion_year is not None:
        action = triggered_actions.get("depletion")
        if action is not None:
            actions.append([action.timing, action.priority, action.action_template])

    if (
        plan.settings.return_model_type is ReturnModelType.MONTE_CARLO
        and forecast.final_total_assets_p10 is not None
        and forecast.final_total_assets_median is not None
        and forecast.final_total_assets_p10 < forecast.final_total_assets_median * Decimal("0.75")
    ):
        action = triggered_actions.get("monte_carlo_downside")
        if action is not None:
            actions.append([action.timing, action.priority, action.action_template])

    return headers, actions


def _bucket_balances_by_year(
    plan: HouseholdPlan,
    forecast: ForecastResult,
) -> dict[int, dict[str, Decimal]]:
    account_to_bucket = {account.account_id: account.bucket_id for account in plan.accounts}
    balances: dict[int, dict[str, Decimal]] = defaultdict(lambda: defaultdict(lambda: Decimal("0.00")))
    for row in forecast.account_rows:
        bucket_id = account_to_bucket.get(row.account_id)
        if not bucket_id:
            continue
        balances[row.year][bucket_id] += row.end_balance
    return {
        year: {bucket_id: amount for bucket_id, amount in bucket_balances.items()}
        for year, bucket_balances in balances.items()
    }


def _bucket_target_floor(plan: HouseholdPlan, bucket: BucketDefinition) -> Decimal:
    years = bucket.target_years
    if years is None:
        years = plan.settings.default_bucket_expense_years
    expense_based_target = plan.settings.planned_annual_spending * Decimal(str(years))
    return _quantize_money(max(bucket.target_amount, expense_based_target))


def _bucket_shortfall_year(
    plan: HouseholdPlan,
    forecast: ForecastResult,
    bucket_id: str,
) -> int | None:
    balances_by_year = _bucket_balances_by_year(plan, forecast)
    bucket = next((item for item in plan.buckets if item.bucket_id == bucket_id), None)
    if bucket is None:
        return None
    target_floor = _bucket_target_floor(plan, bucket)
    if target_floor <= 0:
        return None
    for row in forecast.rows:
        if balances_by_year.get(row.year, {}).get(bucket_id, Decimal("0.00")) < target_floor:
            return row.year
    return None


def _forecast_depletion_year(rows: list[HouseholdForecastRow]) -> int | None:
    for row in rows:
        if row.total_ending_assets <= 0:
            return row.year
    return None


def _depletion_probability_by_year(
    depletion_years: list[int | None],
    target_year: int,
) -> float:
    if not depletion_years:
        return 0.0
    depleted_count = sum(
        1
        for depletion_year in depletion_years
        if depletion_year is not None and depletion_year <= target_year
    )
    return depleted_count / len(depletion_years)


def _append_formatted_row(
    sheet,
    values: list[object],
    number_formats_by_column: dict[int, str],
) -> None:
    row_index = sheet.max_row + 1
    for column_index, value in enumerate(values, start=1):
        cell = sheet.cell(row_index, column_index, value)
        number_format = number_formats_by_column.get(column_index)
        if number_format:
            cell.number_format = number_format


def _format_money(value: Decimal) -> str:
    return f"${float(value):,.2f}"


def _round_amount_for_export(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _round_amount_for_preview(value: Decimal) -> int:
    return _round_amount_for_export(value)


def _format_percent(value: float) -> str:
    return f"{value:.2%}"


def _format_yes_no(value: bool) -> str:
    return "Yes" if value else "No"


def _quantize_money(value: Decimal | int | float | str) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"))
