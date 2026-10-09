from decimal import Decimal

from retirement_financial_tracking.domain.models import (
    Account,
    AccountOwner,
    CashFlowCategory,
    HouseholdPlan,
    Person,
    ProjectionSettings,
    RecurringCashFlow,
    TaxTreatment,
)
from retirement_financial_tracking.io import export_case_workbook, import_case_workbook
from retirement_financial_tracking.services.forecasting import generate_forecast


def test_forecast_rolls_balances_forward_by_year():
    plan = HouseholdPlan(
        plan_id="case-1",
        household_name="Doe Household",
        base_year=2026,
        people=[
            Person(person_id="p1", display_name="John", birth_year=1965),
        ],
        accounts=[
            Account(
                account_id="acct-taxable",
                account_name="Taxable Brokerage",
                owner=AccountOwner.PRIMARY,
                tax_treatment=TaxTreatment.TAXABLE,
                opening_balance=Decimal("100000.00"),
                expected_annual_return_rate=0.05,
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
        people=[Person(person_id="p1", display_name="Jane", birth_year=1970)],
        accounts=[
            Account(
                account_id="acct-1",
                account_name="IRA",
                owner=AccountOwner.PRIMARY,
                tax_treatment=TaxTreatment.TAX_DEFERRED,
                opening_balance=Decimal("750000.00"),
                expected_annual_return_rate=0.06,
            )
        ],
        cash_flows=[
            RecurringCashFlow(
                flow_id="tax-1",
                flow_name="Estimated Taxes",
                category=CashFlowCategory.TAX,
                annual_amount=Decimal("9000.00"),
                start_year=2026,
                end_year=2028,
            )
        ],
    )

    path = tmp_path / "case.xlsx"
    export_case_workbook(path, plan)
    imported = import_case_workbook(path)

    assert imported.plan_id == "case-2"
    assert imported.household_name == "Example Household"
    assert imported.accounts[0].account_name == "IRA"
    assert imported.cash_flows[0].category is CashFlowCategory.TAX
