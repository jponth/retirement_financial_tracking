from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from openpyxl import Workbook, load_workbook

from retirement_financial_tracking.domain.models import (
    Account,
    AccountOwner,
    CashFlowCategory,
    ForecastResult,
    HouseholdPlan,
    Person,
    RecurringCashFlow,
    TaxTreatment,
)


def export_case_workbook(
    path: str | Path,
    plan: HouseholdPlan,
    forecast: ForecastResult | None = None,
) -> Path:
    workbook = Workbook()
    _write_household_sheet(workbook, plan)
    _write_people_sheet(workbook, plan)
    _write_accounts_sheet(workbook, plan)
    _write_cash_flows_sheet(workbook, plan)
    if forecast is not None:
        _write_forecast_sheet(workbook, forecast)
    destination = Path(path)
    workbook.save(destination)
    return destination


def import_case_workbook(path: str | Path) -> HouseholdPlan:
    workbook = load_workbook(Path(path), data_only=True)
    household_sheet = workbook["Household"]
    people_sheet = workbook["People"]
    accounts_sheet = workbook["Accounts"]
    cash_flows_sheet = workbook["Cash Flows"]

    plan_data = {
        row[0].value: row[1].value for row in household_sheet.iter_rows(min_row=2, max_col=2)
    }
    people = [
        Person(
            person_id=row[0].value,
            display_name=row[1].value,
            birth_year=int(row[2].value),
        )
        for row in people_sheet.iter_rows(min_row=2)
        if row[0].value
    ]
    accounts = [
        Account(
            account_id=row[0].value,
            account_name=row[1].value,
            owner=AccountOwner(row[2].value),
            tax_treatment=TaxTreatment(row[3].value),
            opening_balance=Decimal(str(row[4].value or 0)),
            expected_annual_return_rate=float(row[5].value or 0.0),
        )
        for row in accounts_sheet.iter_rows(min_row=2)
        if row[0].value
    ]
    cash_flows = [
        RecurringCashFlow(
            flow_id=row[0].value,
            flow_name=row[1].value,
            category=CashFlowCategory(row[2].value),
            annual_amount=Decimal(str(row[3].value or 0)),
            start_year=int(row[4].value),
            end_year=int(row[5].value),
            annual_growth_rate=float(row[6].value or 0.0),
            target_account_id=row[7].value or None,
        )
        for row in cash_flows_sheet.iter_rows(min_row=2)
        if row[0].value
    ]
    return HouseholdPlan(
        plan_id=plan_data["plan_id"],
        household_name=plan_data["household_name"],
        base_year=int(plan_data["base_year"]),
        people=people,
        accounts=accounts,
        cash_flows=cash_flows,
    )


def _write_household_sheet(workbook: Workbook, plan: HouseholdPlan) -> None:
    sheet = workbook.active
    sheet.title = "Household"
    sheet.append(["field", "value"])
    sheet.append(["plan_id", plan.plan_id])
    sheet.append(["household_name", plan.household_name])
    sheet.append(["base_year", plan.base_year])


def _write_people_sheet(workbook: Workbook, plan: HouseholdPlan) -> None:
    sheet = workbook.create_sheet("People")
    sheet.append(["person_id", "display_name", "birth_year"])
    for person in plan.people:
        sheet.append([person.person_id, person.display_name, person.birth_year])


def _write_accounts_sheet(workbook: Workbook, plan: HouseholdPlan) -> None:
    sheet = workbook.create_sheet("Accounts")
    sheet.append(
        [
            "account_id",
            "account_name",
            "owner",
            "tax_treatment",
            "opening_balance",
            "expected_annual_return_rate",
        ]
    )
    for account in plan.accounts:
        sheet.append(
            [
                account.account_id,
                account.account_name,
                account.owner.value,
                account.tax_treatment.value,
                float(account.opening_balance),
                account.expected_annual_return_rate,
            ]
        )


def _write_cash_flows_sheet(workbook: Workbook, plan: HouseholdPlan) -> None:
    sheet = workbook.create_sheet("Cash Flows")
    sheet.append(
        [
            "flow_id",
            "flow_name",
            "category",
            "annual_amount",
            "start_year",
            "end_year",
            "annual_growth_rate",
            "target_account_id",
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
                flow.target_account_id or "",
            ]
        )


def _write_forecast_sheet(workbook: Workbook, forecast: ForecastResult) -> None:
    sheet = workbook.create_sheet("Forecast")
    sheet.append(
        [
            "year",
            "income_total",
            "expense_total",
            "tax_total",
            "contribution_total",
            "withdrawal_total",
            "net_cash_flow",
            "total_starting_assets",
            "total_ending_assets",
        ]
    )
    for row in forecast.rows:
        sheet.append(
            [
                row.year,
                float(row.income_total),
                float(row.expense_total),
                float(row.tax_total),
                float(row.contribution_total),
                float(row.withdrawal_total),
                float(row.net_cash_flow),
                float(row.total_starting_assets),
                float(row.total_ending_assets),
            ]
        )

