from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from retirement_financial_tracking.domain.models import (
    AccountForecastRow,
    CashFlowCategory,
    ForecastResult,
    HouseholdForecastRow,
    HouseholdPlan,
    ProjectionSettings,
    quantize_money,
    sum_money,
)


def generate_forecast(plan: HouseholdPlan, settings: ProjectionSettings) -> ForecastResult:
    balances: dict[str, Decimal] = {
        account.account_id: account.opening_balance for account in plan.accounts
    }
    rows: list[HouseholdForecastRow] = []
    account_rows: list[AccountForecastRow] = []

    for year in range(settings.start_year, settings.start_year + settings.number_of_years):
        yearly_cash_flows = _collect_cash_flows_for_year(plan, year)
        total_starting_assets = sum_money(balances.values())
        contribution_total = Decimal("0.00")
        withdrawal_total = Decimal("0.00")

        for account in plan.accounts:
            start_balance = balances[account.account_id]
            contributions = yearly_cash_flows["contributions"][account.account_id]
            withdrawals = yearly_cash_flows["withdrawals"][account.account_id]
            growth_base = start_balance + contributions - withdrawals
            investment_growth = quantize_money(
                growth_base * Decimal(str(account.expected_annual_return_rate))
            )
            end_balance = quantize_money(growth_base + investment_growth)
            balances[account.account_id] = end_balance
            contribution_total += contributions
            withdrawal_total += withdrawals
            account_rows.append(
                AccountForecastRow(
                    year=year,
                    account_id=account.account_id,
                    account_name=account.account_name,
                    start_balance=start_balance,
                    contributions=contributions,
                    withdrawals=withdrawals,
                    investment_growth=investment_growth,
                    end_balance=end_balance,
                )
            )

        income_total = yearly_cash_flows["income_total"]
        expense_total = yearly_cash_flows["expense_total"]
        tax_total = yearly_cash_flows["tax_total"]
        total_ending_assets = sum_money(balances.values())
        net_cash_flow = quantize_money(
            income_total - expense_total - tax_total - contribution_total + withdrawal_total
        )
        rows.append(
            HouseholdForecastRow(
                year=year,
                income_total=income_total,
                expense_total=expense_total,
                tax_total=tax_total,
                contribution_total=quantize_money(contribution_total),
                withdrawal_total=quantize_money(withdrawal_total),
                net_cash_flow=net_cash_flow,
                total_starting_assets=total_starting_assets,
                total_ending_assets=total_ending_assets,
            )
        )

    return ForecastResult(plan_id=plan.plan_id, rows=rows, account_rows=account_rows)


def _collect_cash_flows_for_year(plan: HouseholdPlan, year: int) -> dict[str, object]:
    contributions: dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))
    withdrawals: dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))
    income_total = Decimal("0.00")
    expense_total = Decimal("0.00")
    tax_total = Decimal("0.00")

    for cash_flow in plan.cash_flows:
        amount = cash_flow.amount_for_year(year)
        if amount == 0:
            continue
        if cash_flow.category is CashFlowCategory.INCOME:
            income_total += amount
        elif cash_flow.category is CashFlowCategory.EXPENSE:
            expense_total += amount
        elif cash_flow.category is CashFlowCategory.TAX:
            tax_total += amount
        elif cash_flow.category is CashFlowCategory.CONTRIBUTION:
            contributions[cash_flow.target_account_id] += amount
        elif cash_flow.category is CashFlowCategory.WITHDRAWAL:
            withdrawals[cash_flow.target_account_id] += amount

    return {
        "contributions": contributions,
        "withdrawals": withdrawals,
        "income_total": quantize_money(income_total),
        "expense_total": quantize_money(expense_total),
        "tax_total": quantize_money(tax_total),
    }

