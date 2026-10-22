from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from openpyxl import Workbook, load_workbook

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
    HouseholdPlan,
    HouseholdSettings,
    Holding,
    Person,
    PersonRole,
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
    _write_accounts_sheet(workbook, plan)
    _write_holdings_sheet(workbook, plan)
    _write_cash_flows_sheet(workbook, plan)
    _write_actual_balances_sheet(workbook, plan)
    if forecast is not None:
        _write_forecast_sheet(workbook, forecast)
        _write_account_forecast_sheet(workbook, forecast)
        if forecast.return_model_type is ReturnModelType.MONTE_CARLO:
            _write_monte_carlo_summary_sheet(workbook, forecast)
        elif "Monte Carlo Summary" in workbook.sheetnames:
            del workbook["Monte Carlo Summary"]
    elif "Monte Carlo Summary" in workbook.sheetnames:
        del workbook["Monte Carlo Summary"]
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


def _write_forecast_sheet(workbook: Workbook, forecast: ForecastResult) -> None:
    sheet = _get_or_create_sheet(workbook, "Forecast")
    _clear_sheet(sheet)
    sheet.append(
        [
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
    )
    for row in forecast.rows:
        sheet.append(
            [
                row.year,
                float(row.explicit_income_total),
                float(row.social_security_total),
                float(row.pension_total),
                float(row.income_total),
                float(row.living_expense_total),
                float(row.healthcare_total),
                float(row.hsa_contribution_total),
                float(row.explicit_expense_total),
                float(row.expense_total),
                float(row.explicit_tax_total),
                float(row.derived_tax_total),
                float(row.tax_total),
                float(row.contribution_total),
                float(row.hsa_healthcare_withdrawal_total),
                float(row.explicit_withdrawal_total),
                float(row.rmd_withdrawal_total),
                float(row.auto_funding_withdrawal_total),
                float(row.withdrawal_total),
                float(row.short_term_ending_assets),
                float(row.intermediate_ending_assets),
                float(row.long_term_ending_assets),
                float(row.net_cash_flow),
                float(row.total_starting_assets),
                float(row.total_ending_assets),
            ]
        )


def _write_account_forecast_sheet(workbook: Workbook, forecast: ForecastResult) -> None:
    sheet = _get_or_create_sheet(workbook, "Account Forecast")
    _clear_sheet(sheet)
    sheet.append(
        [
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
    )
    for row in forecast.account_rows:
        sheet.append(
            [
                row.year,
                row.account_id,
                row.account_name,
                row.bucket_type.value,
                row.effective_annual_return_rate,
                float(row.start_balance),
                float(row.contributions),
                float(row.explicit_withdrawals),
                float(row.rmd_withdrawals),
                float(row.hsa_healthcare_withdrawals),
                float(row.auto_funding_withdrawals),
                float(row.replenishment_inflows),
                float(row.replenishment_outflows),
                float(row.withdrawals),
                float(row.investment_growth),
                float(row.end_balance),
            ]
        )


def _write_monte_carlo_summary_sheet(workbook: Workbook, forecast: ForecastResult) -> None:
    if forecast.return_model_type is not ReturnModelType.MONTE_CARLO:
        return
    sheet = _get_or_create_sheet(workbook, "Monte Carlo Summary")
    _clear_sheet(sheet)
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
