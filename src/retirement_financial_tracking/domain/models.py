from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Iterable

from pydantic import BaseModel, Field, model_validator


TWOPLACES = Decimal("0.01")


def quantize_money(value: Decimal | int | float | str) -> Decimal:
    return Decimal(str(value)).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


class AccountOwner(str, Enum):
    PRIMARY = "primary"
    SPOUSE = "spouse"
    JOINT = "joint"


class TaxTreatment(str, Enum):
    TAXABLE = "taxable"
    TAX_DEFERRED = "tax_deferred"
    TAX_FREE = "tax_free"
    HSA = "hsa"


class CashFlowCategory(str, Enum):
    INCOME = "income"
    EXPENSE = "expense"
    TAX = "tax"
    CONTRIBUTION = "contribution"
    WITHDRAWAL = "withdrawal"


class Person(BaseModel):
    person_id: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    birth_year: int = Field(ge=1900, le=2200)


class Account(BaseModel):
    account_id: str = Field(min_length=1)
    account_name: str = Field(min_length=1)
    owner: AccountOwner
    tax_treatment: TaxTreatment
    opening_balance: Decimal = Field(default=Decimal("0.00"))
    expected_annual_return_rate: float = Field(default=0.0, ge=-1.0, le=5.0)

    @model_validator(mode="after")
    def _normalize_opening_balance(self) -> "Account":
        self.opening_balance = quantize_money(self.opening_balance)
        return self


class RecurringCashFlow(BaseModel):
    flow_id: str = Field(min_length=1)
    flow_name: str = Field(min_length=1)
    category: CashFlowCategory
    annual_amount: Decimal = Field(default=Decimal("0.00"))
    start_year: int = Field(ge=1900, le=2200)
    end_year: int = Field(ge=1900, le=2200)
    annual_growth_rate: float = Field(default=0.0, ge=-1.0, le=5.0)
    target_account_id: str | None = None

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


class HouseholdPlan(BaseModel):
    plan_id: str = Field(min_length=1)
    household_name: str = Field(min_length=1)
    base_year: int = Field(ge=1900, le=2200)
    people: list[Person] = Field(min_length=1)
    accounts: list[Account] = Field(default_factory=list)
    cash_flows: list[RecurringCashFlow] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_references(self) -> "HouseholdPlan":
        account_ids = {account.account_id for account in self.accounts}
        for cash_flow in self.cash_flows:
            if cash_flow.target_account_id and cash_flow.target_account_id not in account_ids:
                raise ValueError(
                    f"Cash flow {cash_flow.flow_id} references unknown account "
                    f"{cash_flow.target_account_id!r}"
                )
        return self


class ProjectionSettings(BaseModel):
    start_year: int = Field(ge=1900, le=2200)
    number_of_years: int = Field(ge=1, le=100)


class AccountForecastRow(BaseModel):
    year: int
    account_id: str
    account_name: str
    start_balance: Decimal
    contributions: Decimal
    withdrawals: Decimal
    investment_growth: Decimal
    end_balance: Decimal


class HouseholdForecastRow(BaseModel):
    year: int
    income_total: Decimal
    expense_total: Decimal
    tax_total: Decimal
    contribution_total: Decimal
    withdrawal_total: Decimal
    net_cash_flow: Decimal
    total_starting_assets: Decimal
    total_ending_assets: Decimal


class ForecastResult(BaseModel):
    plan_id: str
    rows: list[HouseholdForecastRow]
    account_rows: list[AccountForecastRow]

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

