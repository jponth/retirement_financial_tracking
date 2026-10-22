from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Iterable

from pydantic import BaseModel, Field, model_validator


TWOPLACES = Decimal("0.01")


def quantize_money(value: Decimal | int | float | str) -> Decimal:
    return Decimal(str(value)).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


class FilingStatus(str, Enum):
    SINGLE = "single"
    MARRIED_FILING_JOINTLY = "married_filing_jointly"
    MARRIED_FILING_SEPARATELY = "married_filing_separately"
    HEAD_OF_HOUSEHOLD = "head_of_household"


class PersonRole(str, Enum):
    PRIMARY = "primary"
    SPOUSE = "spouse"
    DEPENDENT = "dependent"


class AccountOwner(str, Enum):
    PRIMARY = "primary"
    SPOUSE = "spouse"
    JOINT = "joint"


class TaxTreatment(str, Enum):
    TAXABLE = "taxable"
    TAX_DEFERRED = "tax_deferred"
    TAX_FREE = "tax_free"
    HSA = "hsa"


class AccountType(str, Enum):
    TAXABLE_BROKERAGE = "taxable_brokerage"
    TRADITIONAL_IRA = "traditional_ira"
    ROTH_IRA = "roth_ira"
    EMPLOYER_401K = "employer_401k"
    HSA = "hsa"
    CASH = "cash"
    CD = "cd"
    ANNUITY = "annuity"
    OTHER = "other"


class BucketType(str, Enum):
    SHORT_TERM = "short_term"
    INTERMEDIATE = "intermediate"
    LONG_TERM = "long_term"
    OTHER = "other"


class CashFlowCategory(str, Enum):
    INCOME = "income"
    EXPENSE = "expense"
    TAX = "tax"
    CONTRIBUTION = "contribution"
    WITHDRAWAL = "withdrawal"


class ReturnModelType(str, Enum):
    SIMPLE = "simple"
    SCENARIO_BASED = "scenario_based"
    MONTE_CARLO = "monte_carlo"


class ReturnScenarioType(str, Enum):
    BASE = "base"
    CONSERVATIVE = "conservative"
    OPTIMISTIC = "optimistic"
    BAD_FIRST_5_YEARS = "bad_first_5_years"


class WithdrawalTaxPriority(str, Enum):
    TAXABLE_TAX_DEFERRED_TAX_FREE = "taxable_tax_deferred_tax_free"
    TAX_DEFERRED_TAXABLE_TAX_FREE = "tax_deferred_taxable_tax_free"
    TAXABLE_TAX_FREE_TAX_DEFERRED = "taxable_tax_free_tax_deferred"


class WithdrawalOwnerPriority(str, Enum):
    OLDER_FIRST = "older_first"
    YOUNGER_FIRST = "younger_first"
    PRIMARY_FIRST = "primary_first"
    SPOUSE_FIRST = "spouse_first"
    PRO_RATA = "pro_rata"


class WithdrawalAccountTypePriority(str, Enum):
    NO_PREFERENCE = "no_preference"
    LIQUID_FIRST = "liquid_first"
    RETIREMENT_FIRST = "retirement_first"


class WithdrawalAllocationMethod(str, Enum):
    DRAIN_ONE_THEN_NEXT = "drain_one_then_next"
    PRO_RATA = "pro_rata"


class RothHandlingPolicy(str, Enum):
    LAST_RESORT = "last_resort"
    NORMAL_PRIORITY = "normal_priority"


class HouseholdSettings(BaseModel):
    state: str = Field(default="CT", min_length=2)
    filing_status: FilingStatus = FilingStatus.MARRIED_FILING_JOINTLY
    projection_years: int = Field(default=30, ge=1, le=100)
    inflation_rate: float = Field(default=0.03, ge=-1.0, le=5.0)
    default_bucket_expense_years: float = Field(default=3.0, ge=0.0, le=100.0)
    return_model_type: ReturnModelType = ReturnModelType.SIMPLE
    return_scenario_type: ReturnScenarioType = ReturnScenarioType.BASE
    monte_carlo_simulations: int = Field(default=250, ge=1, le=10000)
    monte_carlo_seed: int | None = Field(default=42, ge=0, le=2_147_483_647)
    monte_carlo_depletion_target_year: int | None = Field(default=None, ge=1900, le=2200)
    monte_carlo_depletion_target_age: int | None = Field(default=None, ge=0, le=130)
    bucket_return_short_term: float = Field(default=0.02, ge=-1.0, le=5.0)
    bucket_return_intermediate: float = Field(default=0.04, ge=-1.0, le=5.0)
    bucket_return_long_term: float = Field(default=0.06, ge=-1.0, le=5.0)
    bucket_return_other: float = Field(default=0.03, ge=-1.0, le=5.0)
    bucket_volatility_short_term: float = Field(default=0.01, ge=0.0, le=5.0)
    bucket_volatility_intermediate: float = Field(default=0.06, ge=0.0, le=5.0)
    bucket_volatility_long_term: float = Field(default=0.12, ge=0.0, le=5.0)
    bucket_volatility_other: float = Field(default=0.08, ge=0.0, le=5.0)
    planned_annual_spending: Decimal = Field(default=Decimal("0.00"))
    target_cash_reserve: Decimal = Field(default=Decimal("0.00"))
    federal_effective_tax_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    state_effective_tax_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    rmd_start_age: int = Field(default=73, ge=50, le=100)
    auto_fund_shortfall: bool = True
    use_withdrawal_priority_policy: bool = True
    withdrawal_tax_priority: WithdrawalTaxPriority = (
        WithdrawalTaxPriority.TAXABLE_TAX_DEFERRED_TAX_FREE
    )
    withdrawal_owner_priority: WithdrawalOwnerPriority = WithdrawalOwnerPriority.OLDER_FIRST
    withdrawal_account_type_priority: WithdrawalAccountTypePriority = (
        WithdrawalAccountTypePriority.NO_PREFERENCE
    )
    withdrawal_allocation_method: WithdrawalAllocationMethod = (
        WithdrawalAllocationMethod.DRAIN_ONE_THEN_NEXT
    )
    roth_handling_policy: RothHandlingPolicy = RothHandlingPolicy.LAST_RESORT
    hsa_contribution_limit_self: Decimal = Field(default=Decimal("4300.00"))
    hsa_contribution_limit_family: Decimal = Field(default=Decimal("8550.00"))
    hsa_catch_up_amount: Decimal = Field(default=Decimal("1000.00"))
    notes: str = ""

    @model_validator(mode="after")
    def _normalize_money(self) -> "HouseholdSettings":
        self.planned_annual_spending = quantize_money(self.planned_annual_spending)
        self.target_cash_reserve = quantize_money(self.target_cash_reserve)
        self.hsa_contribution_limit_self = quantize_money(self.hsa_contribution_limit_self)
        self.hsa_contribution_limit_family = quantize_money(self.hsa_contribution_limit_family)
        self.hsa_catch_up_amount = quantize_money(self.hsa_catch_up_amount)
        return self


class Person(BaseModel):
    person_id: str = Field(min_length=1)
    role: PersonRole = PersonRole.PRIMARY
    display_name: str = Field(min_length=1)
    birth_year: int = Field(ge=1900, le=2200)
    retirement_year: int | None = Field(default=None, ge=1900, le=2200)
    life_expectancy: int | None = Field(default=None, ge=1, le=130)
    social_security_claim_age: float | None = Field(default=None, ge=0.0, le=100.0)
    estimated_monthly_social_security: Decimal = Field(default=Decimal("0.00"))
    pension_start_age: float | None = Field(default=None, ge=0.0, le=100.0)
    estimated_monthly_pension: Decimal = Field(default=Decimal("0.00"))
    pension_indexed: bool = False
    medicare_start_year: int | None = Field(default=None, ge=1900, le=2200)
    annual_healthcare_premium: Decimal = Field(default=Decimal("0.00"))
    annual_healthcare_out_of_pocket: Decimal = Field(default=Decimal("0.00"))
    hsa_eligible: bool = False
    desired_annual_hsa_contribution: Decimal = Field(default=Decimal("0.00"))

    @model_validator(mode="after")
    def _normalize_money(self) -> "Person":
        self.estimated_monthly_social_security = quantize_money(
            self.estimated_monthly_social_security
        )
        self.estimated_monthly_pension = quantize_money(self.estimated_monthly_pension)
        self.annual_healthcare_premium = quantize_money(self.annual_healthcare_premium)
        self.annual_healthcare_out_of_pocket = quantize_money(
            self.annual_healthcare_out_of_pocket
        )
        self.desired_annual_hsa_contribution = quantize_money(
            self.desired_annual_hsa_contribution
        )
        return self


class BucketDefinition(BaseModel):
    bucket_id: str = Field(min_length=1)
    bucket_name: str = Field(min_length=1)
    bucket_type: BucketType
    target_amount: Decimal = Field(default=Decimal("0.00"))
    target_years: float | None = Field(default=None, ge=0.0, le=100.0)
    replenishment_source_bucket_id: str | None = None
    notes: str = ""

    @model_validator(mode="after")
    def _normalize_money(self) -> "BucketDefinition":
        self.target_amount = quantize_money(self.target_amount)
        return self


class Account(BaseModel):
    account_id: str = Field(min_length=1)
    account_name: str = Field(min_length=1)
    account_type: AccountType = AccountType.OTHER
    owner: AccountOwner
    custodian: str = ""
    tax_treatment: TaxTreatment
    opening_balance: Decimal = Field(default=Decimal("0.00"))
    expected_annual_return_rate: float = Field(default=0.0, ge=-1.0, le=5.0)
    bucket_id: str | None = None
    contribution_allowed: bool = True
    withdrawal_allowed: bool = True
    roth_conversion_source_allowed: bool = False

    @model_validator(mode="after")
    def _normalize_opening_balance(self) -> "Account":
        self.opening_balance = quantize_money(self.opening_balance)
        return self


class Holding(BaseModel):
    holding_id: str = Field(min_length=1)
    account_id: str = Field(min_length=1)
    holding_name: str = Field(min_length=1)
    ticker: str = ""
    asset_class: str = ""
    market_value: Decimal = Field(default=Decimal("0.00"))
    bucket_id: str | None = None
    maturity_year: int | None = Field(default=None, ge=1900, le=2200)
    fdic_issuer: str = ""
    notes: str = ""

    @model_validator(mode="after")
    def _normalize_money(self) -> "Holding":
        self.market_value = quantize_money(self.market_value)
        return self


class RecurringCashFlow(BaseModel):
    flow_id: str = Field(min_length=1)
    flow_name: str = Field(min_length=1)
    category: CashFlowCategory
    annual_amount: Decimal = Field(default=Decimal("0.00"))
    start_year: int = Field(ge=1900, le=2200)
    end_year: int = Field(ge=1900, le=2200)
    annual_growth_rate: float = Field(default=0.0, ge=-1.0, le=5.0)
    person_id: str | None = None
    target_account_id: str | None = None
    notes: str = ""

    @model_validator(mode="after")
    def _validate_and_normalize(self) -> "RecurringCashFlow":
        self.annual_amount = quantize_money(self.annual_amount)
        if self.end_year < self.start_year:
            raise ValueError("end_year must be greater than or equal to start_year")
        if self.category in {CashFlowCategory.CONTRIBUTION, CashFlowCategory.WITHDRAWAL}:
            if not self.target_account_id:
                raise ValueError("account cash flows require target_account_id")
        return self

    def applies_to_year(self, year: int) -> bool:
        return self.start_year <= year <= self.end_year

    def amount_for_year(self, year: int) -> Decimal:
        if not self.applies_to_year(year):
            return Decimal("0.00")
        offset = year - self.start_year
        growth_factor = Decimal(str((1 + self.annual_growth_rate) ** offset))
        return quantize_money(self.annual_amount * growth_factor)


class ActualBalanceSnapshot(BaseModel):
    snapshot_id: str = Field(min_length=1)
    account_id: str = Field(min_length=1)
    as_of_date: str = Field(min_length=1)
    balance: Decimal = Field(default=Decimal("0.00"))
    source: str = ""

    @model_validator(mode="after")
    def _normalize_money(self) -> "ActualBalanceSnapshot":
        self.balance = quantize_money(self.balance)
        return self


class HouseholdPlan(BaseModel):
    plan_id: str = Field(min_length=1)
    household_name: str = Field(min_length=1)
    base_year: int = Field(ge=1900, le=2200)
    settings: HouseholdSettings = Field(default_factory=HouseholdSettings)
    people: list[Person] = Field(min_length=1)
    buckets: list[BucketDefinition] = Field(default_factory=list)
    accounts: list[Account] = Field(default_factory=list)
    holdings: list[Holding] = Field(default_factory=list)
    cash_flows: list[RecurringCashFlow] = Field(default_factory=list)
    actual_balance_snapshots: list[ActualBalanceSnapshot] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_references(self) -> "HouseholdPlan":
        _ensure_unique_ids("Person", (person.person_id for person in self.people))
        _ensure_unique_ids("Bucket", (bucket.bucket_id for bucket in self.buckets))
        _ensure_unique_ids("Account", (account.account_id for account in self.accounts))
        _ensure_unique_ids("Holding", (holding.holding_id for holding in self.holdings))
        _ensure_unique_ids("Cash flow", (cash_flow.flow_id for cash_flow in self.cash_flows))
        _ensure_unique_ids(
            "Snapshot",
            (snapshot.snapshot_id for snapshot in self.actual_balance_snapshots),
        )

        account_ids = {account.account_id for account in self.accounts}
        bucket_ids = {bucket.bucket_id for bucket in self.buckets}
        person_ids = {person.person_id for person in self.people}

        for account in self.accounts:
            if account.bucket_id and account.bucket_id not in bucket_ids:
                raise ValueError(
                    f"Account {account.account_id} references unknown bucket {account.bucket_id!r}"
                )
        for bucket in self.buckets:
            if (
                bucket.replenishment_source_bucket_id
                and bucket.replenishment_source_bucket_id not in bucket_ids
            ):
                raise ValueError(
                    f"Bucket {bucket.bucket_id} references unknown replenishment source "
                    f"{bucket.replenishment_source_bucket_id!r}"
                )
            if bucket.replenishment_source_bucket_id == bucket.bucket_id:
                raise ValueError(
                    f"Bucket {bucket.bucket_id} cannot replenish from itself"
                )
        for holding in self.holdings:
            if holding.account_id not in account_ids:
                raise ValueError(
                    f"Holding {holding.holding_id} references unknown account "
                    f"{holding.account_id!r}"
                )
            if holding.bucket_id and holding.bucket_id not in bucket_ids:
                raise ValueError(
                    f"Holding {holding.holding_id} references unknown bucket "
                    f"{holding.bucket_id!r}"
                )
        for cash_flow in self.cash_flows:
            if cash_flow.person_id and cash_flow.person_id not in person_ids:
                raise ValueError(
                    f"Cash flow {cash_flow.flow_id} references unknown person "
                    f"{cash_flow.person_id!r}"
                )
            if cash_flow.target_account_id and cash_flow.target_account_id not in account_ids:
                raise ValueError(
                    f"Cash flow {cash_flow.flow_id} references unknown account "
                    f"{cash_flow.target_account_id!r}"
                )
        for snapshot in self.actual_balance_snapshots:
            if snapshot.account_id not in account_ids:
                raise ValueError(
                    f"Snapshot {snapshot.snapshot_id} references unknown account "
                    f"{snapshot.account_id!r}"
                )
        return self


class ProjectionSettings(BaseModel):
    start_year: int = Field(ge=1900, le=2200)
    number_of_years: int = Field(ge=1, le=100)


class AccountForecastRow(BaseModel):
    year: int
    account_id: str
    account_name: str
    bucket_type: BucketType
    effective_annual_return_rate: float
    start_balance: Decimal
    contributions: Decimal
    explicit_withdrawals: Decimal
    rmd_withdrawals: Decimal
    hsa_healthcare_withdrawals: Decimal
    auto_funding_withdrawals: Decimal
    replenishment_inflows: Decimal
    replenishment_outflows: Decimal
    withdrawals: Decimal
    investment_growth: Decimal
    end_balance: Decimal


class HouseholdForecastRow(BaseModel):
    year: int
    explicit_income_total: Decimal
    social_security_total: Decimal
    pension_total: Decimal
    income_total: Decimal
    living_expense_total: Decimal
    healthcare_total: Decimal
    hsa_contribution_total: Decimal
    explicit_expense_total: Decimal
    expense_total: Decimal
    explicit_tax_total: Decimal
    derived_tax_total: Decimal
    tax_total: Decimal
    contribution_total: Decimal
    hsa_healthcare_withdrawal_total: Decimal
    explicit_withdrawal_total: Decimal
    rmd_withdrawal_total: Decimal
    auto_funding_withdrawal_total: Decimal
    withdrawal_total: Decimal
    short_term_ending_assets: Decimal
    intermediate_ending_assets: Decimal
    long_term_ending_assets: Decimal
    net_cash_flow: Decimal
    total_starting_assets: Decimal
    total_ending_assets: Decimal


class ForecastResult(BaseModel):
    plan_id: str
    rows: list[HouseholdForecastRow]
    account_rows: list[AccountForecastRow]
    return_model_type: ReturnModelType = ReturnModelType.SIMPLE
    monte_carlo_simulations: int | None = None
    monte_carlo_seed: int | None = None
    final_total_assets_p10: Decimal | None = None
    final_total_assets_median: Decimal | None = None
    final_total_assets_p90: Decimal | None = None
    monte_carlo_trial_depletion_years: list[int | None] = Field(default_factory=list)

    @property
    def final_total_assets(self) -> Decimal:
        if not self.rows:
            return Decimal("0.00")
        return self.rows[-1].total_ending_assets


def sum_money(values: Iterable[Decimal]) -> Decimal:
    total = Decimal("0.00")
    for value in values:
        total += value
    return quantize_money(total)


def _ensure_unique_ids(label: str, ids: Iterable[str]) -> None:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for item_id in ids:
        if item_id in seen:
            duplicates.add(item_id)
        else:
            seen.add(item_id)
    if duplicates:
        duplicate_list = ", ".join(sorted(duplicates))
        raise ValueError(f"Duplicate {label.lower()} IDs are not allowed: {duplicate_list}")
