from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Mapping, Sequence

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
    ProjectionSettings,
    RecurringCashFlow,
    RothHandlingPolicy,
    ReturnModelType,
    ReturnScenarioType,
    TaxTreatment,
    WithdrawalAccountTypePriority,
    WithdrawalAllocationMethod,
    WithdrawalOwnerPriority,
    WithdrawalTaxPriority,
)
from retirement_financial_tracking.io import export_case_workbook, import_case_workbook
from retirement_financial_tracking.services import generate_forecast


DEFAULT_SAMPLE_NAME = "2-Bucket Sample"
EXPORT_MODE_NEW_FILE = "new_file"
EXPORT_MODE_SAVE_UPDATED_COPY = "save_updated_copy"
EXPORT_MODE_UPDATE_IMPORTED_WORKBOOK = "update_imported_workbook"
DEFAULT_EXPORT_DIRECTORY = str(Path(__file__).resolve().parents[2] / "exports")
PLAN_UI_SCALAR_KEYS = [
    "plan_id",
    "household_name",
    "base_year",
    "state",
    "filing_status",
    "projection_years",
    "inflation_rate",
    "default_bucket_expense_years",
    "return_model_type",
    "return_scenario_type",
    "monte_carlo_simulations",
    "monte_carlo_seed",
    "monte_carlo_depletion_target_year",
    "monte_carlo_depletion_target_age",
    "bucket_return_short_term",
    "bucket_return_intermediate",
    "bucket_return_long_term",
    "bucket_return_other",
    "bucket_volatility_short_term",
    "bucket_volatility_intermediate",
    "bucket_volatility_long_term",
    "bucket_volatility_other",
    "planned_annual_spending",
    "target_cash_reserve",
    "federal_effective_tax_rate",
    "state_effective_tax_rate",
    "rmd_start_age",
    "auto_fund_shortfall",
    "use_withdrawal_priority_policy",
    "withdrawal_tax_priority",
    "withdrawal_owner_priority",
    "withdrawal_account_type_priority",
    "withdrawal_allocation_method",
    "roth_handling_policy",
    "hsa_contribution_limit_self",
    "hsa_contribution_limit_family",
    "hsa_catch_up_amount",
    "notes",
]
PLAN_UI_TABLE_KEYS = [
    "people",
    "buckets",
    "accounts",
    "cash_flows",
    "holdings",
    "snapshots",
]
PLAN_UI_INPUT_KEYS = PLAN_UI_SCALAR_KEYS + PLAN_UI_TABLE_KEYS


@dataclass(frozen=True, slots=True)
class UIPlanPayload:
    scalars: dict[str, object]
    tables: dict[str, object]

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, object]) -> "UIPlanPayload":
        missing = [key for key in PLAN_UI_INPUT_KEYS if key not in mapping]
        if missing:
            raise ValueError(f"Missing UI plan payload keys: {', '.join(missing)}")
        return cls(
            scalars={key: mapping[key] for key in PLAN_UI_SCALAR_KEYS},
            tables={key: mapping[key] for key in PLAN_UI_TABLE_KEYS},
        )

    @classmethod
    def from_ordered_values(cls, values: Sequence[object]) -> "UIPlanPayload":
        if len(values) != len(PLAN_UI_INPUT_KEYS):
            raise ValueError(
                f"Expected {len(PLAN_UI_INPUT_KEYS)} UI plan values, got {len(values)}"
            )
        return cls.from_mapping(dict(zip(PLAN_UI_INPUT_KEYS, values, strict=True)))

    def get(self, key: str) -> object:
        if key in self.scalars:
            return self.scalars[key]
        return self.tables[key]

    def as_dict(self) -> dict[str, object]:
        return {**self.scalars, **self.tables}


def _format_amount_for_ui(value: Decimal | float | int) -> str:
    rounded = int(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return f"{rounded:,}"


def _format_rate_for_ui(value: float | Decimal | int) -> float:
    return round(float(value), 2)


def _normalize_numeric_input(value: object, default: int | float = 0) -> object:
    if value in (None, ""):
        return default
    if isinstance(value, str):
        normalized = value.strip().replace(",", "")
        return normalized if normalized != "" else default
    return value


def sample_plan_names() -> list[str]:
    return [DEFAULT_SAMPLE_NAME, "3-Bucket Sample"]


def sample_plan(sample_name: str = DEFAULT_SAMPLE_NAME) -> HouseholdPlan:
    if sample_name == "3-Bucket Sample":
        return _sample_plan_three_bucket()
    return _sample_plan_two_bucket()


def _sample_plan_two_bucket() -> HouseholdPlan:
    return HouseholdPlan(
        plan_id="sample-case-1",
        household_name="2-Bucket Sample Household",
        base_year=2026,
        settings=HouseholdSettings(
            state="CT",
            filing_status=FilingStatus.MARRIED_FILING_JOINTLY,
            projection_years=30,
            inflation_rate=0.03,
            default_bucket_expense_years=3.0,
            return_model_type=ReturnModelType.SIMPLE,
            return_scenario_type=ReturnScenarioType.BASE,
            monte_carlo_simulations=250,
            monte_carlo_seed=42,
            monte_carlo_depletion_target_year=None,
            monte_carlo_depletion_target_age=None,
            bucket_return_short_term=0.02,
            bucket_return_intermediate=0.04,
            bucket_return_long_term=0.06,
            bucket_return_other=0.03,
            bucket_volatility_short_term=0.01,
            bucket_volatility_intermediate=0.06,
            bucket_volatility_long_term=0.12,
            bucket_volatility_other=0.08,
            planned_annual_spending=Decimal("96000.00"),
            target_cash_reserve=Decimal("69000.00"),
            federal_effective_tax_rate=0.18,
            state_effective_tax_rate=0.05,
            rmd_start_age=73,
            auto_fund_shortfall=True,
            use_withdrawal_priority_policy=True,
            withdrawal_tax_priority=WithdrawalTaxPriority.TAXABLE_TAX_DEFERRED_TAX_FREE,
            withdrawal_owner_priority=WithdrawalOwnerPriority.OLDER_FIRST,
            withdrawal_account_type_priority=WithdrawalAccountTypePriority.NO_PREFERENCE,
            withdrawal_allocation_method=WithdrawalAllocationMethod.DRAIN_ONE_THEN_NEXT,
            roth_handling_policy=RothHandlingPolicy.LAST_RESORT,
            hsa_contribution_limit_self=Decimal("4300.00"),
            hsa_contribution_limit_family=Decimal("8550.00"),
            hsa_catch_up_amount=Decimal("1000.00"),
            notes="Starter sample case.",
        ),
        people=[
            Person(
                person_id="p1",
                role=PersonRole.PRIMARY,
                display_name="Primary Owner",
                birth_year=1965,
                retirement_year=2028,
                life_expectancy=92,
                social_security_claim_age=67.0,
                estimated_monthly_social_security=Decimal("3200.00"),
                pension_start_age=63.0,
                estimated_monthly_pension=Decimal("500.00"),
                pension_indexed=False,
                medicare_start_year=2030,
                annual_healthcare_premium=Decimal("8400.00"),
                annual_healthcare_out_of_pocket=Decimal("2500.00"),
                hsa_eligible=True,
                desired_annual_hsa_contribution=Decimal("4300.00"),
            ),
            Person(
                person_id="p2",
                role=PersonRole.SPOUSE,
                display_name="Spouse",
                birth_year=1967,
                retirement_year=2030,
                life_expectancy=90,
                social_security_claim_age=67.0,
                estimated_monthly_social_security=Decimal("2500.00"),
                pension_start_age=65.0,
                estimated_monthly_pension=Decimal("750.00"),
                pension_indexed=True,
                medicare_start_year=2032,
                annual_healthcare_premium=Decimal("7200.00"),
                annual_healthcare_out_of_pocket=Decimal("2200.00"),
                desired_annual_hsa_contribution=Decimal("2000.00"),
            ),
        ],
        buckets=[
            BucketDefinition(
                bucket_id="b1",
                bucket_name="Short-Term",
                bucket_type=BucketType.SHORT_TERM,
                target_amount=Decimal("469000.00"),
                target_years=3.0,
                replenishment_source_bucket_id="b3",
                notes="Short-term reserve",
            ),
            BucketDefinition(
                bucket_id="b3",
                bucket_name="Long-Term",
                bucket_type=BucketType.LONG_TERM,
                target_amount=Decimal("1876065.00"),
                target_years=20.0,
                notes="Long-term growth",
            ),
        ],
        accounts=[
            Account(
                account_id="acct-1",
                account_name="Traditional IRA",
                account_type=AccountType.TRADITIONAL_IRA,
                owner=AccountOwner.PRIMARY,
                custodian="Fidelity",
                tax_treatment=TaxTreatment.TAX_DEFERRED,
                opening_balance=Decimal("1800000.00"),
                expected_annual_return_rate=0.06,
                bucket_id="b3",
                contribution_allowed=False,
                roth_conversion_source_allowed=True,
            ),
            Account(
                account_id="acct-2",
                account_name="Roth IRA",
                account_type=AccountType.ROTH_IRA,
                owner=AccountOwner.PRIMARY,
                custodian="Fidelity",
                tax_treatment=TaxTreatment.TAX_FREE,
                opening_balance=Decimal("400000.00"),
                expected_annual_return_rate=0.06,
                bucket_id="b3",
            ),
            Account(
                account_id="acct-3",
                account_name="Cash Reserve",
                account_type=AccountType.CASH,
                owner=AccountOwner.JOINT,
                custodian="Bank",
                tax_treatment=TaxTreatment.TAXABLE,
                opening_balance=Decimal("69000.00"),
                expected_annual_return_rate=0.02,
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
                market_value=Decimal("800000.00"),
                bucket_id="b3",
            ),
            Holding(
                holding_id="h2",
                account_id="acct-3",
                holding_name="Cash",
                asset_class="cash",
                market_value=Decimal("69000.00"),
                bucket_id="b1",
            ),
        ],
        cash_flows=[
            RecurringCashFlow(
                flow_id="cf1",
                flow_name="IRA Withdrawal",
                category=CashFlowCategory.WITHDRAWAL,
                annual_amount=Decimal("70000.00"),
                start_year=2026,
                end_year=2035,
                target_account_id="acct-1",
            ),
            RecurringCashFlow(
                flow_id="cf2",
                flow_name="Extra Travel",
                category=CashFlowCategory.EXPENSE,
                annual_amount=Decimal("6000.00"),
                start_year=2026,
                end_year=2028,
                annual_growth_rate=0.02,
                notes="Temporary discretionary spending",
            ),
        ],
        actual_balance_snapshots=[
            ActualBalanceSnapshot(
                snapshot_id="s1",
                account_id="acct-1",
                as_of_date="2026-01-31",
                balance=Decimal("1792500.00"),
                source="Manual import",
            )
        ],
    )


def _sample_plan_three_bucket() -> HouseholdPlan:
    return HouseholdPlan(
        plan_id="sample-case-3-bucket",
        household_name="3-Bucket Sample Household",
        base_year=2026,
        settings=HouseholdSettings(
            state="CT",
            filing_status=FilingStatus.MARRIED_FILING_JOINTLY,
            projection_years=30,
            inflation_rate=0.03,
            default_bucket_expense_years=3.0,
            return_model_type=ReturnModelType.SCENARIO_BASED,
            return_scenario_type=ReturnScenarioType.BASE,
            monte_carlo_simulations=250,
            monte_carlo_seed=42,
            monte_carlo_depletion_target_year=None,
            monte_carlo_depletion_target_age=None,
            bucket_return_short_term=0.02,
            bucket_return_intermediate=0.04,
            bucket_return_long_term=0.06,
            bucket_return_other=0.03,
            bucket_volatility_short_term=0.01,
            bucket_volatility_intermediate=0.06,
            bucket_volatility_long_term=0.12,
            bucket_volatility_other=0.08,
            planned_annual_spending=Decimal("96000.00"),
            target_cash_reserve=Decimal("69000.00"),
            federal_effective_tax_rate=0.18,
            state_effective_tax_rate=0.05,
            rmd_start_age=73,
            auto_fund_shortfall=True,
            use_withdrawal_priority_policy=True,
            withdrawal_tax_priority=WithdrawalTaxPriority.TAXABLE_TAX_DEFERRED_TAX_FREE,
            withdrawal_owner_priority=WithdrawalOwnerPriority.OLDER_FIRST,
            withdrawal_account_type_priority=WithdrawalAccountTypePriority.NO_PREFERENCE,
            withdrawal_allocation_method=WithdrawalAllocationMethod.DRAIN_ONE_THEN_NEXT,
            roth_handling_policy=RothHandlingPolicy.LAST_RESORT,
            hsa_contribution_limit_self=Decimal("4300.00"),
            hsa_contribution_limit_family=Decimal("8550.00"),
            hsa_catch_up_amount=Decimal("1000.00"),
            notes="Starter 3-bucket sample case.",
        ),
        people=[
            Person(
                person_id="p1",
                role=PersonRole.PRIMARY,
                display_name="Primary Owner",
                birth_year=1965,
                retirement_year=2028,
                life_expectancy=92,
                social_security_claim_age=67.0,
                estimated_monthly_social_security=Decimal("3200.00"),
                pension_start_age=63.0,
                estimated_monthly_pension=Decimal("500.00"),
                pension_indexed=False,
                medicare_start_year=2030,
                annual_healthcare_premium=Decimal("8400.00"),
                annual_healthcare_out_of_pocket=Decimal("2500.00"),
                hsa_eligible=True,
                desired_annual_hsa_contribution=Decimal("4300.00"),
            ),
            Person(
                person_id="p2",
                role=PersonRole.SPOUSE,
                display_name="Spouse",
                birth_year=1967,
                retirement_year=2030,
                life_expectancy=90,
                social_security_claim_age=67.0,
                estimated_monthly_social_security=Decimal("2500.00"),
                pension_start_age=65.0,
                estimated_monthly_pension=Decimal("750.00"),
                pension_indexed=True,
                medicare_start_year=2032,
                annual_healthcare_premium=Decimal("7200.00"),
                annual_healthcare_out_of_pocket=Decimal("2200.00"),
                desired_annual_hsa_contribution=Decimal("2000.00"),
            ),
        ],
        buckets=[
            BucketDefinition(
                bucket_id="b1",
                bucket_name="Short-Term",
                bucket_type=BucketType.SHORT_TERM,
                target_amount=Decimal("469000.00"),
                target_years=3.0,
                replenishment_source_bucket_id="b2",
                notes="Short-term reserve",
            ),
            BucketDefinition(
                bucket_id="b2",
                bucket_name="Intermediate",
                bucket_type=BucketType.INTERMEDIATE,
                target_amount=Decimal("600000.00"),
                target_years=3.0,
                replenishment_source_bucket_id="b3",
                notes="Intermediate stability",
            ),
            BucketDefinition(
                bucket_id="b3",
                bucket_name="Long-Term",
                bucket_type=BucketType.LONG_TERM,
                target_amount=Decimal("1276065.00"),
                target_years=20.0,
                notes="Long-term growth",
            ),
        ],
        accounts=[
            Account(
                account_id="acct-1",
                account_name="Traditional IRA",
                account_type=AccountType.TRADITIONAL_IRA,
                owner=AccountOwner.PRIMARY,
                custodian="Fidelity",
                tax_treatment=TaxTreatment.TAX_DEFERRED,
                opening_balance=Decimal("1200000.00"),
                expected_annual_return_rate=0.06,
                bucket_id="b3",
                contribution_allowed=False,
                roth_conversion_source_allowed=True,
            ),
            Account(
                account_id="acct-2",
                account_name="Bond Allocation",
                account_type=AccountType.TAXABLE_BROKERAGE,
                owner=AccountOwner.JOINT,
                custodian="Vanguard",
                tax_treatment=TaxTreatment.TAXABLE,
                opening_balance=Decimal("600000.00"),
                expected_annual_return_rate=0.04,
                bucket_id="b2",
            ),
            Account(
                account_id="acct-3",
                account_name="Cash Reserve",
                account_type=AccountType.CASH,
                owner=AccountOwner.JOINT,
                custodian="Bank",
                tax_treatment=TaxTreatment.TAXABLE,
                opening_balance=Decimal("69000.00"),
                expected_annual_return_rate=0.02,
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
                market_value=Decimal("800000.00"),
                bucket_id="b3",
            ),
            Holding(
                holding_id="h2",
                account_id="acct-2",
                holding_name="BND",
                ticker="BND",
                asset_class="bond",
                market_value=Decimal("600000.00"),
                bucket_id="b2",
            ),
            Holding(
                holding_id="h3",
                account_id="acct-3",
                holding_name="Cash",
                asset_class="cash",
                market_value=Decimal("69000.00"),
                bucket_id="b1",
            ),
        ],
        cash_flows=[
            RecurringCashFlow(
                flow_id="cf1",
                flow_name="IRA Withdrawal",
                category=CashFlowCategory.WITHDRAWAL,
                annual_amount=Decimal("70000.00"),
                start_year=2026,
                end_year=2035,
                target_account_id="acct-1",
            ),
            RecurringCashFlow(
                flow_id="cf2",
                flow_name="Extra Travel",
                category=CashFlowCategory.EXPENSE,
                annual_amount=Decimal("6000.00"),
                start_year=2026,
                end_year=2028,
                annual_growth_rate=0.02,
                notes="Temporary discretionary spending",
            ),
        ],
        actual_balance_snapshots=[
            ActualBalanceSnapshot(
                snapshot_id="s1",
                account_id="acct-1",
                as_of_date="2026-01-31",
                balance=Decimal("1192500.00"),
                source="Manual import",
            )
        ],
    )


def plan_to_ui_values(plan: HouseholdPlan) -> dict[str, object]:
    return {
        "plan_id": plan.plan_id,
        "household_name": plan.household_name,
        "base_year": plan.base_year,
        "state": plan.settings.state,
        "filing_status": plan.settings.filing_status.value,
        "projection_years": plan.settings.projection_years,
        "inflation_rate": plan.settings.inflation_rate,
        "default_bucket_expense_years": plan.settings.default_bucket_expense_years,
        "return_model_type": plan.settings.return_model_type.value,
        "return_scenario_type": plan.settings.return_scenario_type.value,
        "monte_carlo_simulations": plan.settings.monte_carlo_simulations,
        "monte_carlo_seed": plan.settings.monte_carlo_seed,
        "monte_carlo_depletion_target_year": plan.settings.monte_carlo_depletion_target_year,
        "monte_carlo_depletion_target_age": plan.settings.monte_carlo_depletion_target_age,
        "bucket_return_short_term": _format_rate_for_ui(plan.settings.bucket_return_short_term),
        "bucket_return_intermediate": _format_rate_for_ui(plan.settings.bucket_return_intermediate),
        "bucket_return_long_term": _format_rate_for_ui(plan.settings.bucket_return_long_term),
        "bucket_return_other": _format_rate_for_ui(plan.settings.bucket_return_other),
        "bucket_volatility_short_term": _format_rate_for_ui(plan.settings.bucket_volatility_short_term),
        "bucket_volatility_intermediate": _format_rate_for_ui(plan.settings.bucket_volatility_intermediate),
        "bucket_volatility_long_term": _format_rate_for_ui(plan.settings.bucket_volatility_long_term),
        "bucket_volatility_other": _format_rate_for_ui(plan.settings.bucket_volatility_other),
        "planned_annual_spending": _format_amount_for_ui(plan.settings.planned_annual_spending),
        "target_cash_reserve": _format_amount_for_ui(plan.settings.target_cash_reserve),
        "federal_effective_tax_rate": _format_rate_for_ui(plan.settings.federal_effective_tax_rate),
        "state_effective_tax_rate": _format_rate_for_ui(plan.settings.state_effective_tax_rate),
        "rmd_start_age": plan.settings.rmd_start_age,
        "auto_fund_shortfall": plan.settings.auto_fund_shortfall,
        "use_withdrawal_priority_policy": plan.settings.use_withdrawal_priority_policy,
        "withdrawal_tax_priority": plan.settings.withdrawal_tax_priority.value,
        "withdrawal_owner_priority": plan.settings.withdrawal_owner_priority.value,
        "withdrawal_account_type_priority": plan.settings.withdrawal_account_type_priority.value,
        "withdrawal_allocation_method": plan.settings.withdrawal_allocation_method.value,
        "roth_handling_policy": plan.settings.roth_handling_policy.value,
        "hsa_contribution_limit_self": _format_amount_for_ui(plan.settings.hsa_contribution_limit_self),
        "hsa_contribution_limit_family": _format_amount_for_ui(plan.settings.hsa_contribution_limit_family),
        "hsa_catch_up_amount": _format_amount_for_ui(plan.settings.hsa_catch_up_amount),
        "notes": plan.settings.notes,
        "people": [
            [
                person.person_id,
                person.role.value,
                person.display_name,
                person.birth_year,
                person.retirement_year,
                person.life_expectancy,
                person.social_security_claim_age,
                _format_amount_for_ui(person.estimated_monthly_social_security),
                person.pension_start_age,
                _format_amount_for_ui(person.estimated_monthly_pension),
                person.pension_indexed,
                person.medicare_start_year,
                _format_amount_for_ui(person.annual_healthcare_premium),
                _format_amount_for_ui(person.annual_healthcare_out_of_pocket),
                person.hsa_eligible,
                _format_amount_for_ui(person.desired_annual_hsa_contribution),
            ]
            for person in plan.people
        ],
        "buckets": [
            [
                bucket.bucket_id,
                bucket.bucket_name,
                bucket.bucket_type.value,
                _format_amount_for_ui(bucket.target_amount),
                bucket.target_years,
                bucket.replenishment_source_bucket_id or "",
                bucket.notes,
            ]
            for bucket in plan.buckets
        ],
        "accounts": [
            [
                account.account_id,
                account.account_name,
                account.account_type.value,
                account.owner.value,
                account.custodian,
                account.tax_treatment.value,
                _format_amount_for_ui(account.opening_balance),
                _format_rate_for_ui(account.expected_annual_return_rate),
                account.bucket_id or "",
                account.contribution_allowed,
                account.withdrawal_allowed,
                account.roth_conversion_source_allowed,
            ]
            for account in plan.accounts
        ],
        "cash_flows": [
            [
                flow.flow_id,
                flow.flow_name,
                flow.category.value,
                _format_amount_for_ui(flow.annual_amount),
                flow.start_year,
                flow.end_year,
                _format_rate_for_ui(flow.annual_growth_rate),
                flow.person_id or "",
                flow.target_account_id or "",
                flow.notes,
            ]
            for flow in plan.cash_flows
        ],
        "holdings": [
            [
                holding.holding_id,
                holding.account_id,
                holding.holding_name,
                holding.ticker,
                holding.asset_class,
                _format_amount_for_ui(holding.market_value),
                holding.bucket_id or "",
                holding.maturity_year,
                holding.fdic_issuer,
                holding.notes,
            ]
            for holding in plan.holdings
        ],
        "snapshots": [
            [
                snapshot.snapshot_id,
                snapshot.account_id,
                snapshot.as_of_date,
                _format_amount_for_ui(snapshot.balance),
                snapshot.source,
            ]
            for snapshot in plan.actual_balance_snapshots
        ],
    }


def ui_values_to_plan(payload: UIPlanPayload | Mapping[str, object]) -> HouseholdPlan:
    if not isinstance(payload, UIPlanPayload):
        payload = UIPlanPayload.from_mapping(payload)

    settings = HouseholdSettings(
        state=(payload.get("state") or "CT").strip(),
        filing_status=FilingStatus(
            payload.get("filing_status") or FilingStatus.MARRIED_FILING_JOINTLY.value
        ),
        projection_years=int(payload.get("projection_years") or 30),
        inflation_rate=float(_normalize_numeric_input(payload.get("inflation_rate"), 0.0)),
        default_bucket_expense_years=float(
            _normalize_numeric_input(payload.get("default_bucket_expense_years"), 0.0)
        ),
        return_model_type=ReturnModelType(
            payload.get("return_model_type") or ReturnModelType.SIMPLE.value
        ),
        return_scenario_type=ReturnScenarioType(
            payload.get("return_scenario_type") or ReturnScenarioType.BASE.value
        ),
        monte_carlo_simulations=int(
            _normalize_numeric_input(payload.get("monte_carlo_simulations"), 250)
        ),
        monte_carlo_seed=_int_or_none_from_value(payload.get("monte_carlo_seed")),
        monte_carlo_depletion_target_year=_int_or_none_from_value(
            payload.get("monte_carlo_depletion_target_year")
        ),
        monte_carlo_depletion_target_age=_int_or_none_from_value(
            payload.get("monte_carlo_depletion_target_age")
        ),
        bucket_return_short_term=float(
            _normalize_numeric_input(payload.get("bucket_return_short_term"), 0.0)
        ),
        bucket_return_intermediate=float(
            _normalize_numeric_input(payload.get("bucket_return_intermediate"), 0.0)
        ),
        bucket_return_long_term=float(
            _normalize_numeric_input(payload.get("bucket_return_long_term"), 0.0)
        ),
        bucket_return_other=float(
            _normalize_numeric_input(payload.get("bucket_return_other"), 0.0)
        ),
        bucket_volatility_short_term=float(
            _normalize_numeric_input(payload.get("bucket_volatility_short_term"), 0.0)
        ),
        bucket_volatility_intermediate=float(
            _normalize_numeric_input(payload.get("bucket_volatility_intermediate"), 0.0)
        ),
        bucket_volatility_long_term=float(
            _normalize_numeric_input(payload.get("bucket_volatility_long_term"), 0.0)
        ),
        bucket_volatility_other=float(
            _normalize_numeric_input(payload.get("bucket_volatility_other"), 0.0)
        ),
        planned_annual_spending=Decimal(
            str(_normalize_numeric_input(payload.get("planned_annual_spending"), 0))
        ),
        target_cash_reserve=Decimal(
            str(_normalize_numeric_input(payload.get("target_cash_reserve"), 0))
        ),
        federal_effective_tax_rate=float(
            _normalize_numeric_input(payload.get("federal_effective_tax_rate"), 0.0)
        ),
        state_effective_tax_rate=float(
            _normalize_numeric_input(payload.get("state_effective_tax_rate"), 0.0)
        ),
        rmd_start_age=int(payload.get("rmd_start_age") or 73),
        auto_fund_shortfall=bool(payload.get("auto_fund_shortfall")),
        use_withdrawal_priority_policy=bool(payload.get("use_withdrawal_priority_policy")),
        withdrawal_tax_priority=WithdrawalTaxPriority(
            payload.get("withdrawal_tax_priority")
            or WithdrawalTaxPriority.TAXABLE_TAX_DEFERRED_TAX_FREE.value
        ),
        withdrawal_owner_priority=WithdrawalOwnerPriority(
            payload.get("withdrawal_owner_priority")
            or WithdrawalOwnerPriority.OLDER_FIRST.value
        ),
        withdrawal_account_type_priority=WithdrawalAccountTypePriority(
            payload.get("withdrawal_account_type_priority")
            or WithdrawalAccountTypePriority.NO_PREFERENCE.value
        ),
        withdrawal_allocation_method=WithdrawalAllocationMethod(
            payload.get("withdrawal_allocation_method")
            or WithdrawalAllocationMethod.DRAIN_ONE_THEN_NEXT.value
        ),
        roth_handling_policy=RothHandlingPolicy(
            payload.get("roth_handling_policy") or RothHandlingPolicy.LAST_RESORT.value
        ),
        hsa_contribution_limit_self=Decimal(
            str(_normalize_numeric_input(payload.get("hsa_contribution_limit_self"), 0))
        ),
        hsa_contribution_limit_family=Decimal(
            str(_normalize_numeric_input(payload.get("hsa_contribution_limit_family"), 0))
        ),
        hsa_catch_up_amount=Decimal(
            str(_normalize_numeric_input(payload.get("hsa_catch_up_amount"), 0))
        ),
        notes=payload.get("notes") or "",
    )
    return HouseholdPlan(
        plan_id=(payload.get("plan_id") or "case-1").strip(),
        household_name=(payload.get("household_name") or "Household").strip(),
        base_year=int(payload.get("base_year") or 2026),
        settings=settings,
        people=_parse_people(payload.get("people")),
        buckets=_parse_buckets(payload.get("buckets")),
        accounts=_parse_accounts(payload.get("accounts")),
        holdings=_parse_holdings(payload.get("holdings")),
        cash_flows=_parse_cash_flows(payload.get("cash_flows")),
        actual_balance_snapshots=_parse_snapshots(payload.get("snapshots")),
    )


def import_plan_to_ui(path: str) -> dict[str, object]:
    plan = import_case_workbook(path)
    return plan_to_ui_values(plan)


def forecast_for_ui(plan: HouseholdPlan) -> tuple[list[list[object]], list[list[object]], str]:
    result = generate_forecast(
        plan,
        ProjectionSettings(
            start_year=plan.base_year,
            number_of_years=plan.settings.projection_years,
        ),
    )
    table = [
        [
            row.year,
            _format_amount_for_ui(row.explicit_income_total),
            _format_amount_for_ui(row.social_security_total),
            _format_amount_for_ui(row.pension_total),
            _format_amount_for_ui(row.income_total),
            _format_amount_for_ui(row.living_expense_total),
            _format_amount_for_ui(row.healthcare_total),
            _format_amount_for_ui(row.hsa_contribution_total),
            _format_amount_for_ui(row.explicit_expense_total),
            _format_amount_for_ui(row.expense_total),
            _format_amount_for_ui(row.explicit_tax_total),
            _format_amount_for_ui(row.derived_tax_total),
            _format_amount_for_ui(row.tax_total),
            _format_amount_for_ui(row.hsa_healthcare_withdrawal_total),
            _format_amount_for_ui(row.explicit_withdrawal_total),
            _format_amount_for_ui(row.rmd_withdrawal_total),
            _format_amount_for_ui(row.auto_funding_withdrawal_total),
            _format_amount_for_ui(row.withdrawal_total),
            _format_amount_for_ui(row.short_term_ending_assets),
            _format_amount_for_ui(row.intermediate_ending_assets),
            _format_amount_for_ui(row.long_term_ending_assets),
            _format_amount_for_ui(row.net_cash_flow),
            _format_amount_for_ui(row.total_starting_assets),
            _format_amount_for_ui(row.total_ending_assets),
        ]
        for row in result.rows
    ]
    account_table = [
        [
            row.year,
            row.account_id,
            row.account_name,
            row.bucket_type.value,
            _format_rate_for_ui(row.effective_annual_return_rate),
            _format_amount_for_ui(row.start_balance),
            _format_amount_for_ui(row.contributions),
            _format_amount_for_ui(row.explicit_withdrawals),
            _format_amount_for_ui(row.rmd_withdrawals),
            _format_amount_for_ui(row.hsa_healthcare_withdrawals),
            _format_amount_for_ui(row.auto_funding_withdrawals),
            _format_amount_for_ui(row.replenishment_inflows),
            _format_amount_for_ui(row.replenishment_outflows),
            _format_amount_for_ui(row.withdrawals),
            _format_amount_for_ui(row.investment_growth),
            _format_amount_for_ui(row.end_balance),
        ]
        for row in result.account_rows
    ]
    depletion_line = _depletion_summary_line(result.rows)
    summary_lines = [
        f"Final projected assets: ${float(result.final_total_assets):,.2f}",
        depletion_line,
        "",
        f"Forecast years: {len(result.rows)}",
        f"Starting year: {result.rows[0].year if result.rows else plan.base_year}",
        f"Return model: {plan.settings.return_model_type.value}",
    ]
    if plan.settings.return_model_type is ReturnModelType.SCENARIO_BASED:
        summary_lines.append(f"Return scenario: {plan.settings.return_scenario_type.value}")
    if plan.settings.return_model_type is ReturnModelType.MONTE_CARLO:
        summary_lines.extend(
            [
                f"Monte Carlo simulations: {result.monte_carlo_simulations or plan.settings.monte_carlo_simulations:,}",
                f"Monte Carlo seed: {result.monte_carlo_seed if result.monte_carlo_seed is not None else 'random'}",
                f"Final assets p10 / median / p90: "
                f"${float(result.final_total_assets_p10 or Decimal('0')):,.2f} / "
                f"${float(result.final_total_assets_median or result.final_total_assets):,.2f} / "
                f"${float(result.final_total_assets_p90 or Decimal('0')):,.2f}",
            ]
        )
        probability_lines = _monte_carlo_probability_summary_lines(plan, result)
        summary_lines.extend(probability_lines)
    summary = "\n".join(summary_lines)
    return table, account_table, summary


def _depletion_summary_line(rows: list[HouseholdForecastRow]) -> str:
    for row in rows:
        if row.total_ending_assets <= 0:
            return f"Money lasts until year: {row.year}"
    if rows:
        return f"Money lasts through year: {rows[-1].year}"
    return "Money lasts until year: n/a"


def _monte_carlo_probability_summary_lines(
    plan: HouseholdPlan,
    result: ForecastResult,
) -> list[str]:
    if not result.monte_carlo_trial_depletion_years:
        return []

    lines: list[str] = []
    target_year = plan.settings.monte_carlo_depletion_target_year
    if target_year is not None:
        probability = _depletion_probability_by_year(
            result.monte_carlo_trial_depletion_years,
            target_year,
        )
        lines.append(
            f"Probability of depletion by year {target_year}: {probability:.0%}"
        )

    target_age = plan.settings.monte_carlo_depletion_target_age
    age_reference_person = _age_reference_person(plan)
    if target_age is not None and age_reference_person is not None:
        target_age_year = age_reference_person.birth_year + int(target_age)
        probability = _depletion_probability_by_year(
            result.monte_carlo_trial_depletion_years,
            target_age_year,
        )
        lines.append(
            f"Probability of depletion by age {target_age} "
            f"({age_reference_person.display_name}, year {target_age_year}): {probability:.0%}"
        )

    return lines


def _depletion_probability_by_year(
    depletion_years: list[int | None],
    target_year: int,
) -> float:
    if not depletion_years:
        return 0.0
    depleted_count = sum(
        1 for depletion_year in depletion_years
        if depletion_year is not None and depletion_year <= target_year
    )
    return depleted_count / len(depletion_years)


def _age_reference_person(plan: HouseholdPlan) -> Person | None:
    for person in plan.people:
        if person.role is PersonRole.PRIMARY:
            return person
    return plan.people[0] if plan.people else None


def export_plan_for_ui(
    plan: HouseholdPlan,
    export_mode: str = EXPORT_MODE_NEW_FILE,
    imported_workbook_path: str | None = None,
    export_directory: str | None = None,
) -> str:
    path = _resolve_export_path(
        plan=plan,
        export_mode=export_mode,
        imported_workbook_path=imported_workbook_path,
        export_directory=export_directory,
    )
    forecast = generate_forecast(
        plan,
        ProjectionSettings(
            start_year=plan.base_year,
            number_of_years=plan.settings.projection_years,
        ),
    )
    export_case_workbook(
        path,
        plan,
        forecast=forecast,
        template_path=imported_workbook_path,
    )
    return str(path)


def _resolve_export_path(
    *,
    plan: HouseholdPlan,
    export_mode: str,
    imported_workbook_path: str | None,
    export_directory: str | None,
) -> Path:
    target_directory = Path(export_directory or DEFAULT_EXPORT_DIRECTORY)
    target_directory.mkdir(parents=True, exist_ok=True)
    imported_name = _imported_workbook_name(imported_workbook_path)

    if export_mode == EXPORT_MODE_UPDATE_IMPORTED_WORKBOOK and imported_name:
        return target_directory / imported_name

    if export_mode == EXPORT_MODE_UPDATE_IMPORTED_WORKBOOK:
        raise ValueError("No imported workbook is available to update")

    if export_mode == EXPORT_MODE_SAVE_UPDATED_COPY and imported_name:
        source_path = target_directory / imported_name
        suffix = source_path.suffix or ".xlsx"
        return _next_available_sibling_path(source_path, f"{source_path.stem}_updated", suffix)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return target_directory / f"{plan.plan_id or 'retirement_case'}_{timestamp}.xlsx"


def _imported_workbook_name(imported_workbook_path: str | None) -> str | None:
    if not imported_workbook_path:
        return None
    path = Path(imported_workbook_path)
    if path.suffix:
        return path.name
    return f"{path.name}.xlsx"


def _next_available_sibling_path(source_path: Path, stem_base: str, suffix: str) -> Path:
    candidate = source_path.with_name(f"{stem_base}{suffix}")
    if not candidate.exists():
        return candidate
    counter = 2
    while True:
        candidate = source_path.with_name(f"{stem_base}_{counter}{suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def _parse_people(rows: list[list[object]]) -> list[Person]:
    people: list[Person] = []
    for row in _normalize_rows(rows):
        if not _has_value(row, 0):
            continue
        people.append(
            Person(
                person_id=str(row[0]),
                role=PersonRole(_str_or_default(row, 1, PersonRole.PRIMARY.value)),
                display_name=_str_or_default(row, 2, "Person"),
                birth_year=int(_num_or_default(row, 3, 1970)),
                retirement_year=_int_or_none(row, 4),
                life_expectancy=_int_or_none(row, 5),
                social_security_claim_age=_float_or_none(row, 6),
                estimated_monthly_social_security=Decimal(str(_num_or_default(row, 7, 0))),
                pension_start_age=_float_or_none(row, 8),
                estimated_monthly_pension=Decimal(str(_num_or_default(row, 9, 0))),
                pension_indexed=_bool_or_default(row, 10, False),
                medicare_start_year=_int_or_none(row, 11),
                annual_healthcare_premium=Decimal(str(_num_or_default(row, 12, 0))),
                annual_healthcare_out_of_pocket=Decimal(str(_num_or_default(row, 13, 0))),
                hsa_eligible=_bool_or_default(row, 14, False),
                desired_annual_hsa_contribution=Decimal(str(_num_or_default(row, 15, 0))),
            )
        )
    return people


def _parse_buckets(rows: list[list[object]]) -> list[BucketDefinition]:
    buckets: list[BucketDefinition] = []
    for row in _normalize_rows(rows):
        if not _has_value(row, 0):
            continue
        buckets.append(
            BucketDefinition(
                bucket_id=str(row[0]),
                bucket_name=_str_or_default(row, 1, "Bucket"),
                bucket_type=BucketType(_str_or_default(row, 2, BucketType.OTHER.value)),
                target_amount=Decimal(str(_num_or_default(row, 3, 0))),
                target_years=_float_or_none(row, 4),
                replenishment_source_bucket_id=_blank_to_none(row[5] if len(row) > 5 else None),
                notes=_str_or_default(row, 6, ""),
            )
        )
    return buckets


def _parse_accounts(rows: list[list[object]]) -> list[Account]:
    accounts: list[Account] = []
    for row in _normalize_rows(rows):
        if not _has_value(row, 0):
            continue
        accounts.append(
            Account(
                account_id=str(row[0]),
                account_name=_str_or_default(row, 1, "Account"),
                account_type=AccountType(_str_or_default(row, 2, AccountType.OTHER.value)),
                owner=AccountOwner(_str_or_default(row, 3, AccountOwner.PRIMARY.value)),
                custodian=_str_or_default(row, 4, ""),
                tax_treatment=TaxTreatment(_str_or_default(row, 5, TaxTreatment.TAXABLE.value)),
                opening_balance=Decimal(str(_num_or_default(row, 6, 0))),
                expected_annual_return_rate=float(_num_or_default(row, 7, 0.0)),
                bucket_id=_blank_to_none(row[8] if len(row) > 8 else None),
                contribution_allowed=_bool_or_default(row, 9, True),
                withdrawal_allowed=_bool_or_default(row, 10, True),
                roth_conversion_source_allowed=_bool_or_default(row, 11, False),
            )
        )
    return accounts


def _parse_cash_flows(rows: list[list[object]]) -> list[RecurringCashFlow]:
    flows: list[RecurringCashFlow] = []
    for row in _normalize_rows(rows):
        if not _has_value(row, 0):
            continue
        flows.append(
            RecurringCashFlow(
                flow_id=str(row[0]),
                flow_name=_str_or_default(row, 1, "Cash Flow"),
                category=CashFlowCategory(_str_or_default(row, 2, CashFlowCategory.EXPENSE.value)),
                annual_amount=Decimal(str(_num_or_default(row, 3, 0))),
                start_year=int(_num_or_default(row, 4, 2026)),
                end_year=int(_num_or_default(row, 5, 2026)),
                annual_growth_rate=float(_num_or_default(row, 6, 0.0)),
                person_id=_blank_to_none(row[7] if len(row) > 7 else None),
                target_account_id=_blank_to_none(row[8] if len(row) > 8 else None),
                notes=_str_or_default(row, 9, ""),
            )
        )
    return flows


def _parse_holdings(rows: list[list[object]]) -> list[Holding]:
    holdings: list[Holding] = []
    for row in _normalize_rows(rows):
        if not _has_value(row, 0):
            continue
        holdings.append(
            Holding(
                holding_id=str(row[0]),
                account_id=_str_or_default(row, 1, ""),
                holding_name=_str_or_default(row, 2, "Holding"),
                ticker=_str_or_default(row, 3, ""),
                asset_class=_str_or_default(row, 4, ""),
                market_value=Decimal(str(_num_or_default(row, 5, 0))),
                bucket_id=_blank_to_none(row[6] if len(row) > 6 else None),
                maturity_year=_int_or_none(row, 7),
                fdic_issuer=_str_or_default(row, 8, ""),
                notes=_str_or_default(row, 9, ""),
            )
        )
    return holdings


def _parse_snapshots(rows: list[list[object]]) -> list[ActualBalanceSnapshot]:
    snapshots: list[ActualBalanceSnapshot] = []
    for row in _normalize_rows(rows):
        if not _has_value(row, 0):
            continue
        snapshots.append(
            ActualBalanceSnapshot(
                snapshot_id=str(row[0]),
                account_id=_str_or_default(row, 1, ""),
                as_of_date=_str_or_default(row, 2, "2026-01-01"),
                balance=Decimal(str(_num_or_default(row, 3, 0))),
                source=_str_or_default(row, 4, ""),
            )
        )
    return snapshots


def _has_value(row: list[object], index: int) -> bool:
    return len(row) > index and row[index] not in (None, "")


def _blank_to_none(value: object) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _str_or_default(row: list[object], index: int, default: str) -> str:
    if len(row) <= index or row[index] in (None, ""):
        return default
    return str(row[index])


def _num_or_default(row: list[object], index: int, default: int | float) -> int | float:
    if len(row) <= index or row[index] in (None, ""):
        return default
    value = row[index]
    if isinstance(value, str):
        normalized = value.strip().replace(",", "")
        if normalized == "":
            return default
        return normalized
    return value


def _int_or_none(row: list[object], index: int) -> int | None:
    if len(row) <= index or row[index] in (None, ""):
        return None
    value = row[index]
    if isinstance(value, str):
        value = value.strip().replace(",", "")
    return int(value)


def _float_or_none(row: list[object], index: int) -> float | None:
    if len(row) <= index or row[index] in (None, ""):
        return None
    value = row[index]
    if isinstance(value, str):
        value = value.strip().replace(",", "")
    return float(value)


def _int_or_none_from_value(value: object) -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, str):
        value = value.strip().replace(",", "")
        if value == "":
            return None
    return int(value)


def _bool_or_default(row: list[object], index: int, default: bool) -> bool:
    if len(row) <= index or row[index] in (None, ""):
        return default
    value = row[index]
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _normalize_rows(rows: Any) -> list[list[object]]:
    if rows is None:
        return []
    values = getattr(rows, "values", None)
    if values is not None and hasattr(values, "tolist"):
        return values.tolist()
    if hasattr(rows, "tolist") and not isinstance(rows, list):
        converted = rows.tolist()
        if isinstance(converted, list):
            return converted
    return rows if isinstance(rows, list) else []
