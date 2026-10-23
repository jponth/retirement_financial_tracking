from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
import math
import random

from retirement_financial_tracking.config.tax_tables import (
    TaxBracket,
    TaxTable,
    load_connecticut_tax_table,
    load_federal_tax_table,
)
from retirement_financial_tracking.domain.models import (
    AccountForecastRow,
    AccountType,
    AccountOwner,
    BucketType,
    CashFlowCategory,
    ForecastResult,
    HouseholdForecastRow,
    HouseholdPlan,
    ProjectionSettings,
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
    quantize_money,
    sum_money,
)


UNIFORM_LIFETIME_DIVISORS = {
    73: Decimal("26.5"),
    74: Decimal("25.5"),
    75: Decimal("24.6"),
    76: Decimal("23.7"),
    77: Decimal("22.9"),
    78: Decimal("22.0"),
    79: Decimal("21.1"),
    80: Decimal("20.2"),
    81: Decimal("19.4"),
    82: Decimal("18.5"),
    83: Decimal("17.7"),
    84: Decimal("16.8"),
    85: Decimal("16.0"),
    86: Decimal("15.2"),
    87: Decimal("14.4"),
    88: Decimal("13.7"),
    89: Decimal("12.9"),
    90: Decimal("12.2"),
    91: Decimal("11.5"),
    92: Decimal("10.8"),
    93: Decimal("10.1"),
    94: Decimal("9.5"),
    95: Decimal("8.9"),
}


RETURN_SCENARIOS = {
    ReturnScenarioType.BASE: {
        BucketType.SHORT_TERM: [0.02, 0.025, 0.02, 0.025, 0.02],
        BucketType.INTERMEDIATE: [0.01, 0.045, 0.03, 0.05, 0.04, 0.04],
        BucketType.LONG_TERM: [-0.10, 0.14, 0.08, 0.10, 0.06, 0.07, 0.06],
        BucketType.OTHER: [0.00, 0.04, 0.03, 0.04, 0.03],
    },
    ReturnScenarioType.CONSERVATIVE: {
        BucketType.SHORT_TERM: [0.02, 0.02, 0.02, 0.02, 0.02],
        BucketType.INTERMEDIATE: [0.00, 0.02, 0.025, 0.03, 0.03],
        BucketType.LONG_TERM: [-0.12, 0.05, 0.04, 0.05, 0.05, 0.05],
        BucketType.OTHER: [0.00, 0.02, 0.02, 0.025, 0.025],
    },
    ReturnScenarioType.OPTIMISTIC: {
        BucketType.SHORT_TERM: [0.025, 0.03, 0.03, 0.03, 0.03],
        BucketType.INTERMEDIATE: [0.03, 0.05, 0.05, 0.055, 0.05],
        BucketType.LONG_TERM: [0.08, 0.12, 0.10, 0.11, 0.09, 0.08],
        BucketType.OTHER: [0.03, 0.05, 0.04, 0.045, 0.04],
    },
    ReturnScenarioType.BAD_FIRST_5_YEARS: {
        BucketType.SHORT_TERM: [0.02, 0.02, 0.02, 0.025, 0.025, 0.025],
        BucketType.INTERMEDIATE: [-0.03, -0.01, 0.00, 0.02, 0.03, 0.04],
        BucketType.LONG_TERM: [-0.18, -0.10, -0.04, 0.05, 0.08, 0.10, 0.08],
        BucketType.OTHER: [-0.05, -0.02, 0.00, 0.02, 0.03, 0.03],
    },
}


def generate_forecast(plan: HouseholdPlan, settings: ProjectionSettings) -> ForecastResult:
    if plan.settings.return_model_type is ReturnModelType.MONTE_CARLO:
        return _generate_monte_carlo_forecast(plan, settings)
    return _generate_deterministic_forecast(
        plan=plan,
        settings=settings,
        rate_provider=lambda account, year_index: _account_return_rate(
            plan=plan,
            account=account,
            year_index=year_index,
        ),
    )


def _generate_deterministic_forecast(
    *,
    plan: HouseholdPlan,
    settings: ProjectionSettings,
    rate_provider,
) -> ForecastResult:
    balances = _build_starting_balances(plan)
    rows: list[HouseholdForecastRow] = []
    account_rows: list[AccountForecastRow] = []

    for year in range(settings.start_year, settings.start_year + settings.number_of_years):
        yearly_cash_flows = _collect_cash_flows_for_year(plan, year)
        automatic_hsa_contributions = _derive_hsa_contributions(plan, year)
        _merge_contributions(yearly_cash_flows["contributions"], automatic_hsa_contributions)
        social_security_total = _derive_social_security_income(plan, year)
        pension_total = _derive_pension_income(plan, settings, year)
        living_expense_total = _derive_living_expense(plan, settings, year)
        healthcare_total = _derive_healthcare_expense(plan, year)
        total_starting_assets = sum_money(balances.values())
        contribution_total = sum_money(yearly_cash_flows["contributions"].values())
        hsa_contribution_total = sum_money(automatic_hsa_contributions.values())
        hsa_healthcare_withdrawal_total = Decimal("0.00")
        explicit_withdrawal_total = Decimal("0.00")
        rmd_withdrawal_total = Decimal("0.00")
        auto_funding_withdrawal_total = Decimal("0.00")

        rmd_withdrawals = _derive_rmd_withdrawals(plan, balances, year)
        hsa_healthcare_withdrawals = _derive_hsa_healthcare_withdrawals(
            plan=plan,
            balances=balances,
            contributions=yearly_cash_flows["contributions"],
            explicit_withdrawals=yearly_cash_flows["withdrawals"],
            healthcare_total=healthcare_total,
        )
        explicit_income_total = yearly_cash_flows["income_total"]
        explicit_expense_total = yearly_cash_flows["expense_total"]
        explicit_tax_total = yearly_cash_flows["tax_total"]
        income_total = quantize_money(explicit_income_total + social_security_total + pension_total)
        expense_total = quantize_money(
            living_expense_total + healthcare_total + explicit_expense_total
        )
        auto_withdrawals: dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))
        derived_tax_total = Decimal("0.00")
        tax_total = Decimal("0.00")
        net_cash_before_auto = Decimal("0.00")
        for _ in range(8):
            explicit_withdrawal_total = Decimal("0.00")
            rmd_withdrawal_total = Decimal("0.00")
            hsa_healthcare_withdrawal_total = Decimal("0.00")
            auto_funding_withdrawal_total = Decimal("0.00")
            taxable_withdrawals = Decimal("0.00")
            for account in plan.accounts:
                account_id = account.account_id
                explicit_amount = yearly_cash_flows["withdrawals"][account_id]
                rmd_amount = rmd_withdrawals[account_id]
                hsa_healthcare_amount = hsa_healthcare_withdrawals[account_id]
                auto_amount = auto_withdrawals[account_id]
                explicit_withdrawal_total += explicit_amount
                rmd_withdrawal_total += rmd_amount
                hsa_healthcare_withdrawal_total += hsa_healthcare_amount
                auto_funding_withdrawal_total += auto_amount
                if account.tax_treatment is TaxTreatment.TAX_DEFERRED:
                    taxable_withdrawals += explicit_amount + rmd_amount + auto_amount

            derived_tax_total = _derive_taxes(
                plan=plan,
                year=year,
                explicit_tax_total=explicit_tax_total,
                explicit_income_total=explicit_income_total + pension_total,
                social_security_total=social_security_total,
                taxable_withdrawals=taxable_withdrawals,
                hsa_contribution_total=hsa_contribution_total,
            )
            tax_total = quantize_money(explicit_tax_total + derived_tax_total)
            net_cash_before_auto = quantize_money(
                income_total
                - expense_total
                - tax_total
                - contribution_total
                + hsa_healthcare_withdrawal_total
                + explicit_withdrawal_total
                + rmd_withdrawal_total
                + auto_funding_withdrawal_total
            )
            if net_cash_before_auto >= 0 or not plan.settings.auto_fund_shortfall:
                break
            updated_auto_withdrawals = _allocate_bucket_funding(
                plan=plan,
                year=year,
                balances=balances,
                contributions=yearly_cash_flows["contributions"],
                explicit_withdrawals=yearly_cash_flows["withdrawals"],
                rmd_withdrawals=rmd_withdrawals,
                hsa_healthcare_withdrawals=hsa_healthcare_withdrawals,
                amount_needed=abs(net_cash_before_auto),
                existing_auto_withdrawals=auto_withdrawals,
            )
            if dict(updated_auto_withdrawals) == dict(auto_withdrawals):
                auto_withdrawals = updated_auto_withdrawals
                break
            auto_withdrawals = updated_auto_withdrawals

        year_account_state: dict[str, dict[str, Decimal | int | str | float | BucketType]] = {}
        for account in plan.accounts:
            start_balance = balances[account.account_id]
            contributions = yearly_cash_flows["contributions"][account.account_id]
            explicit_withdrawals = yearly_cash_flows["withdrawals"][account.account_id]
            rmd_amount = rmd_withdrawals[account.account_id]
            hsa_healthcare_amount = hsa_healthcare_withdrawals[account.account_id]
            auto_amount = auto_withdrawals[account.account_id]
            bucket_type = _account_bucket_type(plan, account.account_id)
            return_rate = rate_provider(account, year - settings.start_year)
            total_withdrawals = explicit_withdrawals + rmd_amount + hsa_healthcare_amount + auto_amount
            growth_base = start_balance + contributions - total_withdrawals
            investment_growth = quantize_money(growth_base * Decimal(str(return_rate)))
            end_balance = quantize_money(growth_base + investment_growth)
            balances[account.account_id] = end_balance
            year_account_state[account.account_id] = {
                "year": year,
                "account_id": account.account_id,
                "account_name": account.account_name,
                "bucket_type": bucket_type,
                "effective_annual_return_rate": return_rate,
                "start_balance": start_balance,
                "contributions": contributions,
                "explicit_withdrawals": quantize_money(explicit_withdrawals),
                "rmd_withdrawals": quantize_money(rmd_amount),
                "hsa_healthcare_withdrawals": quantize_money(hsa_healthcare_amount),
                "auto_funding_withdrawals": quantize_money(auto_amount),
                "withdrawals": quantize_money(total_withdrawals),
                "investment_growth": investment_growth,
            }

        replenishment_inflows, replenishment_outflows = _apply_bucket_replenishment(
            plan=plan,
            year=year,
            balances=balances,
        )
        for account in plan.accounts:
            account_id = account.account_id
            account_rows.append(
                AccountForecastRow(
                    year=year_account_state[account_id]["year"],
                    account_id=account_id,
                    account_name=year_account_state[account_id]["account_name"],
                    bucket_type=year_account_state[account_id]["bucket_type"],
                    effective_annual_return_rate=year_account_state[account_id]["effective_annual_return_rate"],
                    start_balance=year_account_state[account_id]["start_balance"],
                    contributions=year_account_state[account_id]["contributions"],
                    explicit_withdrawals=year_account_state[account_id]["explicit_withdrawals"],
                    rmd_withdrawals=year_account_state[account_id]["rmd_withdrawals"],
                    hsa_healthcare_withdrawals=year_account_state[account_id]["hsa_healthcare_withdrawals"],
                    auto_funding_withdrawals=year_account_state[account_id]["auto_funding_withdrawals"],
                    replenishment_inflows=replenishment_inflows[account_id],
                    replenishment_outflows=replenishment_outflows[account_id],
                    withdrawals=year_account_state[account_id]["withdrawals"],
                    investment_growth=year_account_state[account_id]["investment_growth"],
                    end_balance=balances[account_id],
                )
            )

        withdrawal_total = quantize_money(
            explicit_withdrawal_total
            + rmd_withdrawal_total
            + hsa_healthcare_withdrawal_total
            + auto_funding_withdrawal_total
        )
        short_term_ending_assets = _bucket_ending_assets(plan, balances, BucketType.SHORT_TERM)
        intermediate_ending_assets = _bucket_ending_assets(plan, balances, BucketType.INTERMEDIATE)
        long_term_ending_assets = _bucket_ending_assets(plan, balances, BucketType.LONG_TERM)
        total_ending_assets = sum_money(balances.values())
        net_cash_flow = net_cash_before_auto
        rows.append(
            HouseholdForecastRow(
                year=year,
                explicit_income_total=explicit_income_total,
                social_security_total=social_security_total,
                pension_total=pension_total,
                income_total=income_total,
                living_expense_total=living_expense_total,
                healthcare_total=healthcare_total,
                hsa_contribution_total=hsa_contribution_total,
                explicit_expense_total=explicit_expense_total,
                expense_total=expense_total,
                explicit_tax_total=explicit_tax_total,
                derived_tax_total=derived_tax_total,
                tax_total=tax_total,
                contribution_total=quantize_money(contribution_total),
                hsa_healthcare_withdrawal_total=quantize_money(hsa_healthcare_withdrawal_total),
                explicit_withdrawal_total=quantize_money(explicit_withdrawal_total),
                rmd_withdrawal_total=quantize_money(rmd_withdrawal_total),
                auto_funding_withdrawal_total=quantize_money(auto_funding_withdrawal_total),
                withdrawal_total=quantize_money(withdrawal_total),
                short_term_ending_assets=short_term_ending_assets,
                intermediate_ending_assets=intermediate_ending_assets,
                long_term_ending_assets=long_term_ending_assets,
                net_cash_flow=net_cash_flow,
                total_starting_assets=total_starting_assets,
                total_ending_assets=total_ending_assets,
            )
        )

    return ForecastResult(
        plan_id=plan.plan_id,
        rows=rows,
        account_rows=account_rows,
        return_model_type=plan.settings.return_model_type,
    )


def _generate_monte_carlo_forecast(
    plan: HouseholdPlan,
    settings: ProjectionSettings,
) -> ForecastResult:
    simulations = plan.settings.monte_carlo_simulations
    rng = random.Random(plan.settings.monte_carlo_seed)
    trial_results: list[ForecastResult] = []

    for _ in range(simulations):
        bucket_returns_by_year = _sample_bucket_returns_for_trial(plan, settings, rng)
        trial_results.append(
            _generate_deterministic_forecast(
                plan=plan,
                settings=settings,
                rate_provider=lambda account, year_index, trial_returns=bucket_returns_by_year: _monte_carlo_return_rate(
                    plan=plan,
                    account=account,
                    year_index=year_index,
                    bucket_returns_by_year=trial_returns,
                ),
            )
        )

    return _aggregate_monte_carlo_results(plan, trial_results)


def _build_starting_balances(plan: HouseholdPlan) -> dict[str, Decimal]:
    latest_snapshots: dict[str, tuple[str, Decimal]] = {}
    for snapshot in plan.actual_balance_snapshots:
        current = latest_snapshots.get(snapshot.account_id)
        if current is None or snapshot.as_of_date > current[0]:
            latest_snapshots[snapshot.account_id] = (snapshot.as_of_date, snapshot.balance)
    balances: dict[str, Decimal] = {}
    for account in plan.accounts:
        snapshot = latest_snapshots.get(account.account_id)
        balances[account.account_id] = snapshot[1] if snapshot is not None else account.opening_balance
    return balances


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


def _merge_contributions(
    base: dict[str, Decimal],
    additions: dict[str, Decimal],
) -> None:
    for account_id, amount in additions.items():
        base[account_id] += amount


def _derive_social_security_income(plan: HouseholdPlan, year: int) -> Decimal:
    total = Decimal("0.00")
    for person in plan.people:
        if person.social_security_claim_age is None:
            continue
        claim_year = person.birth_year + math.floor(person.social_security_claim_age)
        if year >= claim_year:
            total += person.estimated_monthly_social_security * Decimal("12")
    return quantize_money(total)


def _derive_pension_income(plan: HouseholdPlan, settings: ProjectionSettings, year: int) -> Decimal:
    total = Decimal("0.00")
    for person in plan.people:
        if person.pension_start_age is None:
            continue
        start_year = person.birth_year + math.floor(person.pension_start_age)
        if year < start_year:
            continue
        amount = person.estimated_monthly_pension * Decimal("12")
        if person.pension_indexed:
            offset = year - max(start_year, settings.start_year)
            growth_factor = Decimal(str((1 + plan.settings.inflation_rate) ** max(offset, 0)))
            amount = amount * growth_factor
        total += amount
    return quantize_money(total)


def _derive_living_expense(
    plan: HouseholdPlan,
    settings: ProjectionSettings,
    year: int,
) -> Decimal:
    if plan.settings.planned_annual_spending == 0:
        return Decimal("0.00")
    offset = year - settings.start_year
    growth_factor = Decimal(str((1 + plan.settings.inflation_rate) ** offset))
    return quantize_money(plan.settings.planned_annual_spending * growth_factor)


def _derive_healthcare_expense(plan: HouseholdPlan, year: int) -> Decimal:
    total = Decimal("0.00")
    for person in plan.people:
        if person.medicare_start_year is not None and year < person.medicare_start_year:
            continue
        total += person.annual_healthcare_premium
        total += person.annual_healthcare_out_of_pocket
    return quantize_money(total)


def _derive_taxes(
    *,
    plan: HouseholdPlan,
    year: int,
    explicit_tax_total: Decimal,
    explicit_income_total: Decimal,
    social_security_total: Decimal,
    taxable_withdrawals: Decimal,
    hsa_contribution_total: Decimal,
) -> Decimal:
    if explicit_tax_total > 0:
        return Decimal("0.00")
    if plan.settings.tax_model is TaxModelType.BRACKET_BASED:
        return _derive_bracket_based_taxes(
            plan=plan,
            year=year,
            explicit_income_total=explicit_income_total,
            social_security_total=social_security_total,
            taxable_withdrawals=taxable_withdrawals,
            hsa_contribution_total=hsa_contribution_total,
        )
    return _derive_effective_taxes(
        plan=plan,
        explicit_income_total=explicit_income_total,
        social_security_total=social_security_total,
        taxable_withdrawals=taxable_withdrawals,
        hsa_contribution_total=hsa_contribution_total,
    )


def _derive_effective_taxes(
    *,
    plan: HouseholdPlan,
    explicit_income_total: Decimal,
    social_security_total: Decimal,
    taxable_withdrawals: Decimal,
    hsa_contribution_total: Decimal,
) -> Decimal:
    total_rate = Decimal(
        str(plan.settings.federal_effective_tax_rate + plan.settings.state_effective_tax_rate)
    )
    if total_rate <= 0:
        return Decimal("0.00")
    taxable_base = explicit_income_total + social_security_total + taxable_withdrawals
    taxable_base -= hsa_contribution_total
    if taxable_base <= 0:
        return Decimal("0.00")
    return quantize_money(taxable_base * total_rate)


def _derive_bracket_based_taxes(
    *,
    plan: HouseholdPlan,
    year: int,
    explicit_income_total: Decimal,
    social_security_total: Decimal,
    taxable_withdrawals: Decimal,
    hsa_contribution_total: Decimal,
) -> Decimal:
    taxable_base = explicit_income_total + social_security_total + taxable_withdrawals
    taxable_base -= hsa_contribution_total
    if taxable_base <= 0:
        return Decimal("0.00")

    filing_status = plan.settings.filing_status
    federal_table = _project_tax_table_for_year(
        load_federal_tax_table(),
        year=year,
        projection_mode=plan.settings.tax_projection_mode,
        inflation_rate=plan.settings.inflation_rate,
    )
    federal_taxable_income = max(
        Decimal("0.00"),
        taxable_base - federal_table.standard_deduction_by_status.get(filing_status, Decimal("0.00")),
    )
    federal_tax = _calculate_progressive_tax(
        federal_taxable_income,
        federal_table.brackets_by_status[filing_status],
    )

    state_tax = Decimal("0.00")
    if plan.settings.state.strip().upper() == "CT":
        state_table = _project_tax_table_for_year(
            load_connecticut_tax_table(),
            year=year,
            projection_mode=plan.settings.tax_projection_mode,
            inflation_rate=plan.settings.inflation_rate,
        )
        exemption = _lookup_income_based_exemption(
            state_table,
            filing_status,
            taxable_base,
        )
        state_taxable_income = max(Decimal("0.00"), taxable_base - exemption)
        state_tax = _calculate_progressive_tax(
            state_taxable_income,
            state_table.brackets_by_status[filing_status],
        )
    return quantize_money(federal_tax + state_tax)


def _project_tax_table_for_year(
    table: TaxTable,
    *,
    year: int,
    projection_mode: TaxProjectionMode,
    inflation_rate: float,
) -> TaxTable:
    if projection_mode is not TaxProjectionMode.INFLATION_ADJUSTED:
        return table
    if year <= table.base_year:
        return table
    growth_factor = Decimal(str((1 + inflation_rate) ** (year - table.base_year)))
    return TaxTable(
        base_year=table.base_year,
        standard_deduction_by_status={
            status: quantize_money(amount * growth_factor)
            for status, amount in table.standard_deduction_by_status.items()
        },
        brackets_by_status={
            status: tuple(
                TaxBracket(
                    upper_bound=None
                    if bracket.upper_bound is None
                    else quantize_money(bracket.upper_bound * growth_factor),
                    rate=bracket.rate,
                )
                for bracket in brackets
            )
            for status, brackets in table.brackets_by_status.items()
        },
        exemption_by_status=None
        if table.exemption_by_status is None
        else {
            status: tuple(
                (
                    None if upper_bound is None else quantize_money(upper_bound * growth_factor),
                    quantize_money(amount * growth_factor),
                )
                for upper_bound, amount in tiers
            )
            for status, tiers in table.exemption_by_status.items()
        },
    )


def _lookup_income_based_exemption(
    table: TaxTable,
    filing_status,
    taxable_income: Decimal,
) -> Decimal:
    if not table.exemption_by_status:
        return Decimal("0.00")
    for upper_bound, amount in table.exemption_by_status.get(filing_status, ()):
        if upper_bound is None or taxable_income <= upper_bound:
            return amount
    return Decimal("0.00")


def _calculate_progressive_tax(
    taxable_income: Decimal,
    brackets: tuple[TaxBracket, ...],
) -> Decimal:
    if taxable_income <= 0:
        return Decimal("0.00")
    total_tax = Decimal("0.00")
    lower_bound = Decimal("0.00")
    for bracket in brackets:
        upper_bound = bracket.upper_bound
        if upper_bound is None:
            taxable_slice = taxable_income - lower_bound
        else:
            taxable_slice = min(taxable_income, upper_bound) - lower_bound
        if taxable_slice > 0:
            total_tax += taxable_slice * bracket.rate
        if upper_bound is None or taxable_income <= upper_bound:
            break
        lower_bound = upper_bound
    return quantize_money(total_tax)


def _derive_hsa_contributions(
    plan: HouseholdPlan,
    year: int,
) -> dict[str, Decimal]:
    contributions: dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))
    eligible_people = [
        person
        for person in plan.people
        if person.hsa_eligible and (person.medicare_start_year is None or year < person.medicare_start_year)
    ]
    if not eligible_people:
        return contributions

    family_limit = len(eligible_people) > 1
    shared_limit = (
        plan.settings.hsa_contribution_limit_family
        if family_limit
        else plan.settings.hsa_contribution_limit_self
    )
    desired_total = sum_money(
        person.desired_annual_hsa_contribution for person in eligible_people
    )
    catch_up_total = Decimal("0.00")
    for person in eligible_people:
        age = year - person.birth_year
        if age >= 55:
            catch_up_total += plan.settings.hsa_catch_up_amount
    capped_total = min(desired_total, quantize_money(shared_limit + catch_up_total))
    if capped_total <= 0:
        return contributions

    allocations = _eligible_hsa_accounts(plan)
    if not allocations:
        return contributions

    desired_by_account: list[tuple[str, Decimal]] = []
    for person in eligible_people:
        account_id = allocations.get(person.role.value)
        if account_id is None:
            account_id = allocations.get("primary") or allocations.get("spouse") or allocations.get("joint")
        if account_id is None:
            continue
        desired_by_account.append((account_id, person.desired_annual_hsa_contribution))
    if not desired_by_account:
        return contributions

    desired_total_for_accounts = sum_money(amount for _, amount in desired_by_account)
    if desired_total_for_accounts <= 0:
        return contributions

    remaining = capped_total
    for index, (account_id, desired_amount) in enumerate(desired_by_account):
        if remaining <= 0:
            break
        if index == len(desired_by_account) - 1:
            allocated = remaining
        else:
            share = Decimal("0.00")
            if desired_total_for_accounts > 0:
                share = quantize_money(capped_total * (desired_amount / desired_total_for_accounts))
            allocated = min(share, remaining)
        contributions[account_id] += quantize_money(allocated)
        remaining = quantize_money(remaining - allocated)
    return contributions


def _eligible_hsa_accounts(plan: HouseholdPlan) -> dict[str, str]:
    result: dict[str, str] = {}
    for account in plan.accounts:
        if account.account_type is not AccountType.HSA:
            continue
        if account.tax_treatment is not TaxTreatment.HSA:
            continue
        if account.owner is AccountOwner.PRIMARY:
            result["primary"] = account.account_id
        elif account.owner is AccountOwner.SPOUSE:
            result["spouse"] = account.account_id
        elif account.owner is AccountOwner.JOINT and "joint" not in result:
            result["joint"] = account.account_id
    return result


def _derive_hsa_healthcare_withdrawals(
    *,
    plan: HouseholdPlan,
    balances: dict[str, Decimal],
    contributions: dict[str, Decimal],
    explicit_withdrawals: dict[str, Decimal],
    healthcare_total: Decimal,
) -> dict[str, Decimal]:
    withdrawals: dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))
    remaining = Decimal(str(healthcare_total))
    if remaining <= 0:
        return withdrawals

    hsa_accounts = [
        account
        for account in plan.accounts
        if account.account_type is AccountType.HSA and account.tax_treatment is TaxTreatment.HSA
    ]
    for account in hsa_accounts:
        available = (
            balances[account.account_id]
            + contributions[account.account_id]
            - explicit_withdrawals[account.account_id]
        )
        if available <= 0:
            continue
        take = min(available, remaining)
        withdrawals[account.account_id] = quantize_money(take)
        remaining = quantize_money(remaining - take)
        if remaining <= 0:
            break
    return withdrawals


def _derive_rmd_withdrawals(
    plan: HouseholdPlan,
    balances: dict[str, Decimal],
    year: int,
) -> dict[str, Decimal]:
    withdrawals: dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))
    for account in plan.accounts:
        if account.tax_treatment is not TaxTreatment.TAX_DEFERRED:
            continue
        person = _account_person(plan, account.owner)
        if person is None:
            continue
        age = year - person.birth_year
        if age < plan.settings.rmd_start_age:
            continue
        divisor = _rmd_divisor_for_age(age)
        if divisor is None or divisor <= 0:
            continue
        balance = balances[account.account_id]
        if balance <= 0:
            continue
        withdrawals[account.account_id] = quantize_money(balance / divisor)
    return withdrawals


def _rmd_divisor_for_age(age: int) -> Decimal | None:
    if age in UNIFORM_LIFETIME_DIVISORS:
        return UNIFORM_LIFETIME_DIVISORS[age]
    if age > max(UNIFORM_LIFETIME_DIVISORS):
        return UNIFORM_LIFETIME_DIVISORS[max(UNIFORM_LIFETIME_DIVISORS)]
    return None


def _account_person(plan: HouseholdPlan, owner: AccountOwner):
    for person in plan.people:
        if owner is AccountOwner.PRIMARY and person.role.value == "primary":
            return person
        if owner is AccountOwner.SPOUSE and person.role.value == "spouse":
            return person
    return None


def _account_owner_ages(plan: HouseholdPlan, owner: AccountOwner, year: int) -> list[int]:
    ages: list[int] = []
    for person in plan.people:
        if owner is AccountOwner.PRIMARY and person.role.value == "primary":
            ages.append(year - person.birth_year)
        elif owner is AccountOwner.SPOUSE and person.role.value == "spouse":
            ages.append(year - person.birth_year)
        elif owner is AccountOwner.JOINT and person.role.value in {"primary", "spouse"}:
            ages.append(year - person.birth_year)
    return ages


def _withdrawal_group_key(plan: HouseholdPlan, account, year: int) -> tuple[object, ...]:
    return (
        _tax_treatment_rank(plan, account),
        _owner_priority_component(plan, account, year),
        _account_type_priority_rank(plan, account),
        _roth_priority_rank(plan, account),
    )


def _withdrawal_sort_key(plan: HouseholdPlan, account, year: int) -> tuple[object, ...]:
    account_index = next(
        (
            index
            for index, candidate in enumerate(plan.accounts)
            if candidate.account_id == account.account_id
        ),
        len(plan.accounts),
    )
    return _withdrawal_group_key(plan, account, year) + (account_index,)


def _tax_treatment_rank(plan: HouseholdPlan, account) -> int:
    priority = plan.settings.withdrawal_tax_priority
    if priority is WithdrawalTaxPriority.TAX_DEFERRED_TAXABLE_TAX_FREE:
        order = {
            TaxTreatment.TAX_DEFERRED: 0,
            TaxTreatment.TAXABLE: 1,
            TaxTreatment.TAX_FREE: 2,
            TaxTreatment.HSA: 3,
        }
    elif priority is WithdrawalTaxPriority.TAXABLE_TAX_FREE_TAX_DEFERRED:
        order = {
            TaxTreatment.TAXABLE: 0,
            TaxTreatment.TAX_FREE: 1,
            TaxTreatment.TAX_DEFERRED: 2,
            TaxTreatment.HSA: 3,
        }
    else:
        order = {
            TaxTreatment.TAXABLE: 0,
            TaxTreatment.TAX_DEFERRED: 1,
            TaxTreatment.TAX_FREE: 2,
            TaxTreatment.HSA: 3,
        }
    return order.get(account.tax_treatment, 99)


def _owner_priority_component(plan: HouseholdPlan, account, year: int) -> tuple[int, int, int]:
    priority = plan.settings.withdrawal_owner_priority
    if priority is WithdrawalOwnerPriority.PRIMARY_FIRST:
        order = {
            AccountOwner.PRIMARY: 0,
            AccountOwner.SPOUSE: 1,
            AccountOwner.JOINT: 2,
        }
        return (order.get(account.owner, 99), 0, 0)
    if priority is WithdrawalOwnerPriority.SPOUSE_FIRST:
        order = {
            AccountOwner.SPOUSE: 0,
            AccountOwner.PRIMARY: 1,
            AccountOwner.JOINT: 2,
        }
        return (order.get(account.owner, 99), 0, 0)
    if priority is WithdrawalOwnerPriority.PRO_RATA:
        return (0, 0, 0)

    owner_ages = _account_owner_ages(plan, account.owner, year)
    if not owner_ages:
        return (99, 0, 0)
    if priority is WithdrawalOwnerPriority.YOUNGER_FIRST:
        age_value = min(owner_ages)
        return (0, age_value, 0)
    age_value = max(owner_ages)
    return (0, -age_value, 0)


def _account_type_priority_rank(plan: HouseholdPlan, account) -> int:
    priority = plan.settings.withdrawal_account_type_priority
    if priority is WithdrawalAccountTypePriority.RETIREMENT_FIRST:
        order = {
            AccountType.TRADITIONAL_IRA: 0,
            AccountType.EMPLOYER_401K: 1,
            AccountType.ANNUITY: 2,
            AccountType.TAXABLE_BROKERAGE: 3,
            AccountType.CASH: 4,
            AccountType.CD: 5,
            AccountType.OTHER: 6,
            AccountType.HSA: 7,
            AccountType.ROTH_IRA: 8,
        }
        return order.get(account.account_type, 99)
    if priority is WithdrawalAccountTypePriority.LIQUID_FIRST:
        order = {
            AccountType.CASH: 0,
            AccountType.CD: 1,
            AccountType.TAXABLE_BROKERAGE: 2,
            AccountType.OTHER: 3,
            AccountType.TRADITIONAL_IRA: 4,
            AccountType.EMPLOYER_401K: 5,
            AccountType.ANNUITY: 6,
            AccountType.HSA: 7,
            AccountType.ROTH_IRA: 8,
        }
        return order.get(account.account_type, 99)
    return 0


def _roth_priority_rank(plan: HouseholdPlan, account) -> int:
    if plan.settings.roth_handling_policy is RothHandlingPolicy.LAST_RESORT:
        if account.tax_treatment is TaxTreatment.TAX_FREE or account.account_type is AccountType.ROTH_IRA:
            return 1
    return 0


def _allocate_amount_across_accounts(
    *,
    plan: HouseholdPlan,
    year: int,
    candidates: list,
    available_by_account: dict[str, Decimal],
    amount_needed: Decimal,
) -> dict[str, Decimal]:
    allocations: dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))
    remaining = quantize_money(amount_needed)
    if remaining <= 0 or not candidates:
        return allocations

    if not plan.settings.use_withdrawal_priority_policy:
        ordered = list(candidates)
        return _allocate_drain_one_then_next(ordered, available_by_account, remaining, allocations)

    allocation_method = plan.settings.withdrawal_allocation_method
    if allocation_method is WithdrawalAllocationMethod.PRO_RATA:
        grouped_candidates: dict[tuple[object, ...], list] = defaultdict(list)
        for account in candidates:
            grouped_candidates[_withdrawal_group_key(plan, account, year)].append(account)
        for group_key in sorted(grouped_candidates):
            if remaining <= 0:
                break
            group_allocations = _allocate_pro_rata(
                grouped_candidates[group_key],
                available_by_account,
                remaining,
            )
            group_total = sum_money(group_allocations.values()) if group_allocations else Decimal("0.00")
            for account_id, amount in group_allocations.items():
                allocations[account_id] += amount
            remaining = quantize_money(remaining - group_total)
        return allocations

    ordered = sorted(
        candidates,
        key=lambda account: _withdrawal_sort_key(plan, account, year),
    )
    return _allocate_drain_one_then_next(ordered, available_by_account, remaining, allocations)


def _allocate_drain_one_then_next(
    ordered_candidates: list,
    available_by_account: dict[str, Decimal],
    remaining: Decimal,
    allocations: dict[str, Decimal],
) -> dict[str, Decimal]:
    for account in ordered_candidates:
        if remaining <= 0:
            break
        available = available_by_account.get(account.account_id, Decimal("0.00"))
        if available <= 0:
            continue
        take = min(available, remaining)
        allocations[account.account_id] += quantize_money(take)
        remaining = quantize_money(remaining - take)
    return allocations


def _allocate_pro_rata(
    candidates: list,
    available_by_account: dict[str, Decimal],
    amount_needed: Decimal,
) -> dict[str, Decimal]:
    allocations: dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))
    active_candidates = [
        account
        for account in candidates
        if available_by_account.get(account.account_id, Decimal("0.00")) > 0
    ]
    if not active_candidates or amount_needed <= 0:
        return allocations

    total_available = sum_money(
        available_by_account.get(account.account_id, Decimal("0.00"))
        for account in active_candidates
    )
    target_total = min(total_available, amount_needed)
    undistributed = quantize_money(target_total)

    for index, account in enumerate(active_candidates):
        account_id = account.account_id
        available = available_by_account.get(account_id, Decimal("0.00"))
        if index == len(active_candidates) - 1:
            allocated = min(available, undistributed)
        else:
            share = quantize_money(target_total * (available / total_available))
            allocated = min(available, share, undistributed)
        allocations[account_id] += quantize_money(allocated)
        undistributed = quantize_money(undistributed - allocated)

    if undistributed > 0:
        for account in active_candidates:
            if undistributed <= 0:
                break
            account_id = account.account_id
            headroom = quantize_money(
                available_by_account.get(account_id, Decimal("0.00")) - allocations[account_id]
            )
            if headroom <= 0:
                continue
            extra = min(headroom, undistributed)
            allocations[account_id] += quantize_money(extra)
            undistributed = quantize_money(undistributed - extra)

    return allocations


def _allocate_bucket_funding(
    *,
    plan: HouseholdPlan,
    year: int,
    balances: dict[str, Decimal],
    contributions: dict[str, Decimal],
    explicit_withdrawals: dict[str, Decimal],
    rmd_withdrawals: dict[str, Decimal],
    hsa_healthcare_withdrawals: dict[str, Decimal],
    amount_needed: Decimal,
    existing_auto_withdrawals: dict[str, Decimal] | None = None,
) -> dict[str, Decimal]:
    remaining = Decimal(str(amount_needed))
    auto_withdrawals: dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))
    if existing_auto_withdrawals:
        for account_id, amount in existing_auto_withdrawals.items():
            auto_withdrawals[account_id] = quantize_money(amount)
    bucket_order = [
        BucketType.SHORT_TERM,
        BucketType.INTERMEDIATE,
        BucketType.LONG_TERM,
        BucketType.OTHER,
    ]
    for bucket_type in bucket_order:
        candidates = [
            account
            for account in plan.accounts
            if account.withdrawal_allowed
            and _account_bucket_type(plan, account.account_id) is bucket_type
        ]
        if not candidates:
            continue
        available_by_account = {
            account.account_id: quantize_money(
                balances[account.account_id]
                + contributions[account.account_id]
                - explicit_withdrawals[account.account_id]
                - rmd_withdrawals[account.account_id]
                - hsa_healthcare_withdrawals[account.account_id]
                - auto_withdrawals[account.account_id]
            )
            for account in candidates
        }
        bucket_allocations = _allocate_amount_across_accounts(
            plan=plan,
            year=year,
            candidates=candidates,
            available_by_account=available_by_account,
            amount_needed=remaining,
        )
        bucket_total = sum_money(bucket_allocations.values()) if bucket_allocations else Decimal("0.00")
        for account_id, amount in bucket_allocations.items():
            auto_withdrawals[account_id] += amount
        remaining = quantize_money(remaining - bucket_total)
        if remaining <= 0:
            return auto_withdrawals
    return auto_withdrawals


def _apply_bucket_replenishment(
    *,
    plan: HouseholdPlan,
    year: int,
    balances: dict[str, Decimal],
) -> tuple[dict[str, Decimal], dict[str, Decimal]]:
    inflows: dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))
    outflows: dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))
    bucket_map = {bucket.bucket_id: bucket for bucket in plan.buckets}

    for bucket in plan.buckets:
        source_bucket_id = bucket.replenishment_source_bucket_id
        if not source_bucket_id:
            continue
        if source_bucket_id not in bucket_map:
            continue

        target_balance = _bucket_balance(plan, balances, bucket.bucket_id)
        target_floor = _bucket_target_floor(plan, bucket)
        deficit = quantize_money(target_floor - target_balance)
        if deficit <= 0:
            continue

        source_balance = _bucket_balance(plan, balances, source_bucket_id)
        if source_balance <= 0:
            continue

        transfer_amount = min(deficit, source_balance)
        if transfer_amount <= 0:
            continue

        _move_bucket_balance(
            plan=plan,
            year=year,
            balances=balances,
            source_bucket_id=source_bucket_id,
            target_bucket_id=bucket.bucket_id,
            amount=transfer_amount,
            inflows=inflows,
            outflows=outflows,
        )

    return inflows, outflows


def _bucket_balance(
    plan: HouseholdPlan,
    balances: dict[str, Decimal],
    bucket_id: str,
) -> Decimal:
    total = Decimal("0.00")
    for account in plan.accounts:
        if account.bucket_id == bucket_id:
            total += balances[account.account_id]
    return quantize_money(total)


def _bucket_target_floor(plan: HouseholdPlan, bucket) -> Decimal:
    years = bucket.target_years
    if years is None:
        years = plan.settings.default_bucket_expense_years
    expense_based_target = quantize_money(
        plan.settings.planned_annual_spending * Decimal(str(years))
    )
    return quantize_money(max(bucket.target_amount, expense_based_target))


def _move_bucket_balance(
    *,
    plan: HouseholdPlan,
    year: int,
    balances: dict[str, Decimal],
    source_bucket_id: str,
    target_bucket_id: str,
    amount: Decimal,
    inflows: dict[str, Decimal],
    outflows: dict[str, Decimal],
) -> None:
    source_accounts = [
        account for account in plan.accounts if account.bucket_id == source_bucket_id
    ]
    target_accounts = [
        account for account in plan.accounts if account.bucket_id == target_bucket_id
    ]
    if not source_accounts or not target_accounts or amount <= 0:
        return

    available_by_account = {
        account.account_id: balances[account.account_id]
        for account in source_accounts
    }
    source_allocations = _allocate_amount_across_accounts(
        plan=plan,
        year=year,
        candidates=source_accounts,
        available_by_account=available_by_account,
        amount_needed=amount,
    )
    transferred = sum_money(source_allocations.values()) if source_allocations else Decimal("0.00")
    for account_id, moved in source_allocations.items():
        balances[account_id] = quantize_money(balances[account_id] - moved)
        outflows[account_id] += quantize_money(moved)
    if transferred <= 0:
        return

    if len(target_accounts) == 1:
        account_id = target_accounts[0].account_id
        balances[account_id] = quantize_money(balances[account_id] + transferred)
        inflows[account_id] += transferred
        return

    current_total = sum_money(balances[account.account_id] for account in target_accounts)
    undistributed = transferred
    for index, account in enumerate(target_accounts):
        account_id = account.account_id
        if index == len(target_accounts) - 1:
            moved = undistributed
        elif current_total > 0:
            moved = quantize_money(
                transferred * (balances[account_id] / current_total)
            )
            moved = min(moved, undistributed)
        else:
            moved = Decimal("0.00")
        balances[account_id] = quantize_money(balances[account_id] + moved)
        inflows[account_id] += moved
        undistributed = quantize_money(undistributed - moved)

    if undistributed > 0:
        fallback_account_id = target_accounts[0].account_id
        balances[fallback_account_id] = quantize_money(
            balances[fallback_account_id] + undistributed
        )
        inflows[fallback_account_id] += undistributed


def _account_bucket_type(plan: HouseholdPlan, account_id: str) -> BucketType:
    account = next((item for item in plan.accounts if item.account_id == account_id), None)
    if account is None or not account.bucket_id:
        return BucketType.OTHER
    bucket = next((item for item in plan.buckets if item.bucket_id == account.bucket_id), None)
    if bucket is None:
        return BucketType.OTHER
    return bucket.bucket_type


def _account_return_rate(
    *,
    plan: HouseholdPlan,
    account,
    year_index: int,
) -> float:
    if not account.bucket_id:
        return account.expected_annual_return_rate

    bucket_type = _account_bucket_type(plan, account.account_id)
    if plan.settings.return_model_type is ReturnModelType.SCENARIO_BASED:
        return _scenario_return_rate(plan.settings.return_scenario_type, bucket_type, year_index)

    if bucket_type is BucketType.SHORT_TERM:
        return plan.settings.bucket_return_short_term
    if bucket_type is BucketType.INTERMEDIATE:
        return plan.settings.bucket_return_intermediate
    if bucket_type is BucketType.LONG_TERM:
        return plan.settings.bucket_return_long_term
    return plan.settings.bucket_return_other


def _monte_carlo_return_rate(
    *,
    plan: HouseholdPlan,
    account,
    year_index: int,
    bucket_returns_by_year: dict[int, dict[BucketType, float]],
) -> float:
    if not account.bucket_id:
        return bucket_returns_by_year[year_index][BucketType.OTHER]

    bucket_type = _account_bucket_type(plan, account.account_id)
    return bucket_returns_by_year[year_index].get(bucket_type, bucket_returns_by_year[year_index][BucketType.OTHER])


def _sample_bucket_returns_for_trial(
    plan: HouseholdPlan,
    settings: ProjectionSettings,
    rng: random.Random,
) -> dict[int, dict[BucketType, float]]:
    results: dict[int, dict[BucketType, float]] = {}
    for year_index in range(settings.number_of_years):
        results[year_index] = {}
        for bucket_type in BucketType:
            mean_return = _bucket_mean_return(plan, bucket_type)
            volatility = _bucket_volatility(plan, bucket_type)
            sampled_return = rng.gauss(mean_return, volatility) if volatility > 0 else mean_return
            results[year_index][bucket_type] = _clamp_return_rate(sampled_return)
    return results


def _bucket_mean_return(plan: HouseholdPlan, bucket_type: BucketType) -> float:
    if bucket_type is BucketType.SHORT_TERM:
        return plan.settings.bucket_return_short_term
    if bucket_type is BucketType.INTERMEDIATE:
        return plan.settings.bucket_return_intermediate
    if bucket_type is BucketType.LONG_TERM:
        return plan.settings.bucket_return_long_term
    return plan.settings.bucket_return_other


def _bucket_volatility(plan: HouseholdPlan, bucket_type: BucketType) -> float:
    if bucket_type is BucketType.SHORT_TERM:
        return plan.settings.bucket_volatility_short_term
    if bucket_type is BucketType.INTERMEDIATE:
        return plan.settings.bucket_volatility_intermediate
    if bucket_type is BucketType.LONG_TERM:
        return plan.settings.bucket_volatility_long_term
    return plan.settings.bucket_volatility_other


def _clamp_return_rate(value: float) -> float:
    return min(max(value, -0.95), 5.0)


def _scenario_return_rate(
    scenario_type: ReturnScenarioType,
    bucket_type: BucketType,
    year_index: int,
) -> float:
    scenario = RETURN_SCENARIOS[scenario_type]
    sequence = scenario.get(bucket_type) or scenario[BucketType.OTHER]
    index = min(max(year_index, 0), len(sequence) - 1)
    return sequence[index]


def _aggregate_monte_carlo_results(
    plan: HouseholdPlan,
    trial_results: list[ForecastResult],
) -> ForecastResult:
    if not trial_results:
        return ForecastResult(
            plan_id=plan.plan_id,
            rows=[],
            account_rows=[],
            return_model_type=ReturnModelType.MONTE_CARLO,
            monte_carlo_simulations=0,
            monte_carlo_seed=plan.settings.monte_carlo_seed,
        )

    template = trial_results[0]
    household_rows: list[HouseholdForecastRow] = []
    account_rows: list[AccountForecastRow] = []

    household_numeric_fields = [
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
    for row_index, template_row in enumerate(template.rows):
        values = {
            field_name: _decimal_percentile(
                [getattr(result.rows[row_index], field_name) for result in trial_results],
                0.5,
            )
            for field_name in household_numeric_fields
        }
        household_rows.append(
            HouseholdForecastRow(
                year=template_row.year,
                **values,
            )
        )

    account_numeric_fields = [
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
    for row_index, template_row in enumerate(template.account_rows):
        aggregated_values = {}
        for field_name in account_numeric_fields:
            field_values = [getattr(result.account_rows[row_index], field_name) for result in trial_results]
            if field_name == "effective_annual_return_rate":
                aggregated_values[field_name] = _float_percentile(field_values, 0.5)
            else:
                aggregated_values[field_name] = _decimal_percentile(field_values, 0.5)
        account_rows.append(
            AccountForecastRow(
                year=template_row.year,
                account_id=template_row.account_id,
                account_name=template_row.account_name,
                bucket_type=template_row.bucket_type,
                **aggregated_values,
            )
        )

    final_assets = [result.final_total_assets for result in trial_results]
    trial_depletion_years = [_depletion_year_for_rows(result.rows) for result in trial_results]
    return ForecastResult(
        plan_id=plan.plan_id,
        rows=household_rows,
        account_rows=account_rows,
        return_model_type=ReturnModelType.MONTE_CARLO,
        monte_carlo_simulations=len(trial_results),
        monte_carlo_seed=plan.settings.monte_carlo_seed,
        final_total_assets_p10=_decimal_percentile(final_assets, 0.10),
        final_total_assets_median=_decimal_percentile(final_assets, 0.50),
        final_total_assets_p90=_decimal_percentile(final_assets, 0.90),
        monte_carlo_trial_depletion_years=trial_depletion_years,
    )


def _decimal_percentile(values: list[Decimal], percentile: float) -> Decimal:
    float_values = [float(value) for value in values]
    return quantize_money(Decimal(str(_interpolated_percentile(float_values, percentile))))


def _float_percentile(values: list[float], percentile: float) -> float:
    return round(_interpolated_percentile(values, percentile), 6)


def _interpolated_percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    clamped_percentile = min(max(percentile, 0.0), 1.0)
    rank = clamped_percentile * (len(sorted_values) - 1)
    lower_index = math.floor(rank)
    upper_index = math.ceil(rank)
    if lower_index == upper_index:
        return float(sorted_values[lower_index])
    lower_value = float(sorted_values[lower_index])
    upper_value = float(sorted_values[upper_index])
    weight = rank - lower_index
    return lower_value + (upper_value - lower_value) * weight


def _depletion_year_for_rows(rows: list[HouseholdForecastRow]) -> int | None:
    for row in rows:
        if row.total_ending_assets <= 0:
            return row.year
    return None


def _bucket_ending_assets(
    plan: HouseholdPlan,
    balances: dict[str, Decimal],
    bucket_type: BucketType,
) -> Decimal:
    total = Decimal("0.00")
    for account in plan.accounts:
        if _account_bucket_type(plan, account.account_id) is bucket_type:
            total += balances[account.account_id]
    return quantize_money(total)
