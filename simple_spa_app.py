from __future__ import annotations

import gradio as gr

from retirement_financial_tracking import load_app_metadata
from retirement_financial_tracking.ui_theme import MOJAVE_SAGE_CSS, mojave_sage_theme
from retirement_financial_tracking.ui_helpers import (
    DEFAULT_SAMPLE_NAME,
    DEFAULT_EXPORT_DIRECTORY,
    EXPORT_MODE_NEW_FILE,
    EXPORT_MODE_SAVE_UPDATED_COPY,
    EXPORT_MODE_UPDATE_IMPORTED_WORKBOOK,
    UIPlanPayload,
    export_plan_for_ui,
    forecast_with_report_for_ui,
    import_plan_to_ui,
    plan_to_ui_values,
    sample_plan,
    sample_plan_names,
    ui_values_to_plan,
)


PEOPLE_HEADERS = [
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

BUCKET_HEADERS = [
    "bucket_id",
    "bucket_name",
    "bucket_type",
    "target_amount",
    "target_years",
    "replenishment_source_bucket_id",
    "notes",
]

ACCOUNT_HEADERS = [
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

CASH_FLOW_HEADERS = [
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

HOLDING_HEADERS = [
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

SNAPSHOT_HEADERS = [
    "snapshot_id",
    "account_id",
    "as_of_date",
    "balance",
    "source",
]

FORECAST_HEADERS = [
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

ACCOUNT_FORECAST_HEADERS = [
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


CSS = (
    MOJAVE_SAGE_CSS
    + """
    .numeric-table th,
    .numeric-table td,
    .numeric-table .header-cell,
    .numeric-table .body-cell {
        font-variant-numeric: tabular-nums;
    }

    #people-table th:nth-child(4),
    #people-table th:nth-child(5),
    #people-table th:nth-child(6),
    #people-table th:nth-child(7),
    #people-table th:nth-child(8),
    #people-table th:nth-child(9),
    #people-table th:nth-child(10),
    #people-table th:nth-child(12),
    #people-table th:nth-child(13),
    #people-table th:nth-child(14),
    #people-table th:nth-child(16),
    #people-table td:nth-child(4),
    #people-table td:nth-child(5),
    #people-table td:nth-child(6),
    #people-table td:nth-child(7),
    #people-table td:nth-child(8),
    #people-table td:nth-child(9),
    #people-table td:nth-child(10),
    #people-table td:nth-child(12),
    #people-table td:nth-child(13),
    #people-table td:nth-child(14),
    #people-table td:nth-child(16),
    #people-table .header-cell[data-heading="3"],
    #people-table .header-cell[data-heading="4"],
    #people-table .header-cell[data-heading="5"],
    #people-table .header-cell[data-heading="6"],
    #people-table .header-cell[data-heading="7"],
    #people-table .header-cell[data-heading="8"],
    #people-table .header-cell[data-heading="9"],
    #people-table .header-cell[data-heading="11"],
    #people-table .header-cell[data-heading="12"],
    #people-table .header-cell[data-heading="13"],
    #people-table .header-cell[data-heading="15"],
    #people-table .body-cell[data-col="3"],
    #people-table .body-cell[data-col="4"],
    #people-table .body-cell[data-col="5"],
    #people-table .body-cell[data-col="6"],
    #people-table .body-cell[data-col="7"],
    #people-table .body-cell[data-col="8"],
    #people-table .body-cell[data-col="9"],
    #people-table .body-cell[data-col="11"],
    #people-table .body-cell[data-col="12"],
    #people-table .body-cell[data-col="13"],
    #people-table .body-cell[data-col="15"],
    #buckets-table th:nth-child(4),
    #buckets-table th:nth-child(5),
    #buckets-table td:nth-child(4),
    #buckets-table td:nth-child(5),
    #buckets-table .header-cell[data-heading="3"],
    #buckets-table .header-cell[data-heading="4"],
    #buckets-table .body-cell[data-col="3"],
    #buckets-table .body-cell[data-col="4"],
    #accounts-table th:nth-child(7),
    #accounts-table th:nth-child(8),
    #accounts-table td:nth-child(7),
    #accounts-table td:nth-child(8),
    #accounts-table .header-cell[data-heading="6"],
    #accounts-table .header-cell[data-heading="7"],
    #accounts-table .body-cell[data-col="6"],
    #accounts-table .body-cell[data-col="7"],
    #cash-flows-table th:nth-child(4),
    #cash-flows-table th:nth-child(5),
    #cash-flows-table th:nth-child(6),
    #cash-flows-table th:nth-child(7),
    #cash-flows-table td:nth-child(4),
    #cash-flows-table td:nth-child(5),
    #cash-flows-table td:nth-child(6),
    #cash-flows-table td:nth-child(7),
    #cash-flows-table .header-cell[data-heading="3"],
    #cash-flows-table .header-cell[data-heading="4"],
    #cash-flows-table .header-cell[data-heading="5"],
    #cash-flows-table .header-cell[data-heading="6"],
    #cash-flows-table .body-cell[data-col="3"],
    #cash-flows-table .body-cell[data-col="4"],
    #cash-flows-table .body-cell[data-col="5"],
    #cash-flows-table .body-cell[data-col="6"],
    #holdings-table th:nth-child(6),
    #holdings-table th:nth-child(8),
    #holdings-table td:nth-child(6),
    #holdings-table td:nth-child(8),
    #holdings-table .header-cell[data-heading="5"],
    #holdings-table .header-cell[data-heading="7"],
    #holdings-table .body-cell[data-col="5"],
    #holdings-table .body-cell[data-col="7"],
    #snapshots-table th:nth-child(4),
    #snapshots-table td:nth-child(4),
    #snapshots-table .header-cell[data-heading="3"],
    #snapshots-table .body-cell[data-col="3"],
    #forecast-table th,
    #forecast-table td,
    #forecast-table .header-cell,
    #forecast-table .body-cell,
    #account-forecast-table th:nth-child(1),
    #account-forecast-table th:nth-child(5),
    #account-forecast-table th:nth-child(6),
    #account-forecast-table th:nth-child(7),
    #account-forecast-table th:nth-child(8),
    #account-forecast-table th:nth-child(9),
    #account-forecast-table th:nth-child(10),
    #account-forecast-table th:nth-child(11),
    #account-forecast-table th:nth-child(12),
    #account-forecast-table th:nth-child(13),
    #account-forecast-table th:nth-child(14),
    #account-forecast-table th:nth-child(15),
    #account-forecast-table th:nth-child(16),
    #account-forecast-table td:nth-child(1),
    #account-forecast-table td:nth-child(5),
    #account-forecast-table td:nth-child(6),
    #account-forecast-table td:nth-child(7),
    #account-forecast-table td:nth-child(8),
    #account-forecast-table td:nth-child(9),
    #account-forecast-table td:nth-child(10),
    #account-forecast-table td:nth-child(11),
    #account-forecast-table td:nth-child(12),
    #account-forecast-table td:nth-child(13),
    #account-forecast-table td:nth-child(14),
    #account-forecast-table td:nth-child(15),
    #account-forecast-table td:nth-child(16) {
        text-align: right !important;
    }

    #account-forecast-table .header-cell[data-heading="0"],
    #account-forecast-table .header-cell[data-heading="4"],
    #account-forecast-table .header-cell[data-heading="5"],
    #account-forecast-table .header-cell[data-heading="6"],
    #account-forecast-table .header-cell[data-heading="7"],
    #account-forecast-table .header-cell[data-heading="8"],
    #account-forecast-table .header-cell[data-heading="9"],
    #account-forecast-table .header-cell[data-heading="10"],
    #account-forecast-table .header-cell[data-heading="11"],
    #account-forecast-table .header-cell[data-heading="12"],
    #account-forecast-table .header-cell[data-heading="13"],
    #account-forecast-table .header-cell[data-heading="14"],
    #account-forecast-table .header-cell[data-heading="15"],
    #account-forecast-table .body-cell[data-col="0"],
    #account-forecast-table .body-cell[data-col="4"],
    #account-forecast-table .body-cell[data-col="5"],
    #account-forecast-table .body-cell[data-col="6"],
    #account-forecast-table .body-cell[data-col="7"],
    #account-forecast-table .body-cell[data-col="8"],
    #account-forecast-table .body-cell[data-col="9"],
    #account-forecast-table .body-cell[data-col="10"],
    #account-forecast-table .body-cell[data-col="11"],
    #account-forecast-table .body-cell[data-col="12"],
    #account-forecast-table .body-cell[data-col="13"],
    #account-forecast-table .body-cell[data-col="14"],
    #account-forecast-table .body-cell[data-col="15"] {
        text-align: right !important;
    }

    #report-overlay {
        position: fixed !important;
        inset: 0;
        z-index: 1000;
        padding: 3vh 4vw;
        background: rgba(51, 47, 34, 0.48);
        overflow-y: auto;
    }

    #report-modal-card {
        max-width: 1100px;
        margin: 0 auto;
        padding: 24px 28px;
        border-radius: 18px;
        background: #F8F3E8;
        border: 1px solid #D8D1BB;
        box-shadow: 0 24px 54px rgba(70, 65, 47, 0.24);
    }

    #report-modal-card table {
        display: block;
        overflow-x: auto;
        white-space: nowrap;
    }

    #report-modal-card h2,
    #report-modal-card h3 {
        color: #332F22;
    }
"""
)


def build_ui() -> gr.Blocks:
    metadata = load_app_metadata()
    defaults = plan_to_ui_values(sample_plan())

    with gr.Blocks(title=metadata.product_display_name) as demo:
        gr.Markdown(f"# {metadata.product_display_name}")
        gr.Markdown(
            "Create or load a retirement case workbook, edit the main planning inputs, "
            "run the forecast, and export the updated case."
        )

        status = gr.Markdown("Ready.")

        with gr.Row():
            sample_selector = gr.Dropdown(
                label="Sample Case",
                choices=sample_plan_names(),
                value=DEFAULT_SAMPLE_NAME,
            )
            load_sample_btn = gr.Button("Load Sample Case", variant="secondary")
            workbook_input = gr.File(label="Import Workbook", type="filepath")
            run_forecast_btn = gr.Button("Run Forecast", variant="primary")
            view_report_btn = gr.Button(
                "View Report",
                variant="secondary",
                interactive=False,
            )
            export_mode = gr.Dropdown(
                label="Export Mode",
                choices=[
                    EXPORT_MODE_SAVE_UPDATED_COPY,
                    EXPORT_MODE_UPDATE_IMPORTED_WORKBOOK,
                    EXPORT_MODE_NEW_FILE,
                ],
                value=EXPORT_MODE_SAVE_UPDATED_COPY,
            )
            export_btn = gr.Button("Export Workbook", variant="secondary")

        with gr.Row():
            export_directory = gr.Textbox(
                label="Target Export Folder",
                value=DEFAULT_EXPORT_DIRECTORY,
            )

        export_file = gr.File(
            label="Exported Workbook",
            elem_id="exported-workbook-file",
            visible=False,
        )
        imported_workbook_path = gr.State(value=None)

        with gr.Row():
            plan_id = gr.Textbox(label="Plan ID", value=defaults["plan_id"])
            household_name = gr.Textbox(label="Household Name", value=defaults["household_name"])
            base_year = gr.Number(label="Base Year", value=defaults["base_year"], precision=0)

        with gr.Row():
            state = gr.Textbox(label="State", value=defaults["state"])
            filing_status = gr.Dropdown(
                label="Filing Status",
                choices=[
                    "single",
                    "married_filing_jointly",
                    "married_filing_separately",
                    "head_of_household",
                ],
                value=defaults["filing_status"],
            )
            projection_years = gr.Number(
                label="Projection Years",
                value=defaults["projection_years"],
                precision=0,
            )

        with gr.Row():
            inflation_rate = gr.Number(label="Inflation Rate", value=defaults["inflation_rate"])
            default_bucket_expense_years = gr.Number(
                label="Default Bucket Expense Years",
                value=defaults["default_bucket_expense_years"],
            )
            return_model_type = gr.Dropdown(
                label="Return Model",
                choices=["simple", "scenario_based", "monte_carlo"],
                value=defaults["return_model_type"],
            )
            return_scenario_type = gr.Dropdown(
                label="Return Scenario",
                choices=["base", "conservative", "optimistic", "bad_first_5_years"],
                value=defaults["return_scenario_type"],
            )

        with gr.Row():
            monte_carlo_simulations = gr.Number(
                label="Monte Carlo Simulations",
                value=defaults["monte_carlo_simulations"],
                precision=0,
            )
            monte_carlo_seed = gr.Number(
                label="Monte Carlo Seed",
                value=defaults["monte_carlo_seed"],
                precision=0,
            )
            monte_carlo_depletion_target_year = gr.Number(
                label="Depletion Target Year",
                value=defaults["monte_carlo_depletion_target_year"],
                precision=0,
            )
            monte_carlo_depletion_target_age = gr.Number(
                label="Depletion Target Age",
                value=defaults["monte_carlo_depletion_target_age"],
                precision=0,
            )

        with gr.Row():
            bucket_return_short_term = gr.Number(
                label="Short-Term Return",
                value=defaults["bucket_return_short_term"],
            )
            bucket_return_intermediate = gr.Number(
                label="Intermediate Return",
                value=defaults["bucket_return_intermediate"],
            )
            bucket_return_long_term = gr.Number(
                label="Long-Term Return",
                value=defaults["bucket_return_long_term"],
            )
            bucket_return_other = gr.Number(
                label="Other/Fallback Return",
                value=defaults["bucket_return_other"],
            )

        with gr.Row():
            bucket_volatility_short_term = gr.Number(
                label="Short-Term Volatility",
                value=defaults["bucket_volatility_short_term"],
            )
            bucket_volatility_intermediate = gr.Number(
                label="Intermediate Volatility",
                value=defaults["bucket_volatility_intermediate"],
            )
            bucket_volatility_long_term = gr.Number(
                label="Long-Term Volatility",
                value=defaults["bucket_volatility_long_term"],
            )
            bucket_volatility_other = gr.Number(
                label="Other/Fallback Volatility",
                value=defaults["bucket_volatility_other"],
            )

        gr.Markdown(
            "Use `Return Model = simple` for fixed annual bucket returns. "
            "Use `scenario_based` to apply the selected year-by-year scenario to bucketed accounts. "
            "Use `monte_carlo` to simulate many randomized yearly bucket returns using the return inputs "
            "as means and the volatility inputs as standard deviations."
        )

        with gr.Row():
            planned_annual_spending = gr.Number(
                label="Planned Annual Spending",
                value=defaults["planned_annual_spending"],
            )
            target_cash_reserve = gr.Number(
                label="Target Cash Reserve",
                value=defaults["target_cash_reserve"],
            )

        with gr.Row():
            tax_model = gr.Dropdown(
                label="Tax Model",
                choices=["effective_rate", "bracket_based"],
                value=defaults["tax_model"],
            )
            tax_projection_mode = gr.Dropdown(
                label="Tax Projection Mode",
                choices=["static", "inflation_adjusted"],
                value=defaults["tax_projection_mode"],
            )
            federal_effective_tax_rate = gr.Number(
                label="Federal Effective Tax Rate",
                value=defaults["federal_effective_tax_rate"],
            )
            state_effective_tax_rate = gr.Number(
                label="State Effective Tax Rate",
                value=defaults["state_effective_tax_rate"],
            )
        with gr.Row():
            rmd_start_age = gr.Number(
                label="RMD Start Age",
                value=defaults["rmd_start_age"],
                precision=0,
            )
            auto_fund_shortfall = gr.Checkbox(
                label="Auto-Fund Shortfall",
                value=defaults["auto_fund_shortfall"],
            )

        with gr.Row():
            hsa_contribution_limit_self = gr.Number(
                label="HSA Self Limit",
                value=defaults["hsa_contribution_limit_self"],
            )
            hsa_contribution_limit_family = gr.Number(
                label="HSA Family Limit",
                value=defaults["hsa_contribution_limit_family"],
            )
            hsa_catch_up_amount = gr.Number(
                label="HSA Catch-Up Amount",
                value=defaults["hsa_catch_up_amount"],
            )

        with gr.Accordion("Withdrawal Priority Policy", open=False):
            gr.Markdown(
                "Bucket draw order is currently fixed as `short_term -> intermediate -> long_term -> other`. "
                "These settings control how accounts are chosen within each bucket after any required RMDs."
            )
            with gr.Row():
                use_withdrawal_priority_policy = gr.Checkbox(
                    label="Use Withdrawal Priority Policy",
                    value=defaults["use_withdrawal_priority_policy"],
                )
                withdrawal_tax_priority = gr.Dropdown(
                    label="Tax Treatment Priority",
                    choices=[
                        "taxable_tax_deferred_tax_free",
                        "tax_deferred_taxable_tax_free",
                        "taxable_tax_free_tax_deferred",
                    ],
                    value=defaults["withdrawal_tax_priority"],
                )
            with gr.Row():
                withdrawal_owner_priority = gr.Dropdown(
                    label="Owner Priority",
                    choices=[
                        "older_first",
                        "younger_first",
                        "primary_first",
                        "spouse_first",
                        "pro_rata",
                    ],
                    value=defaults["withdrawal_owner_priority"],
                )
                withdrawal_account_type_priority = gr.Dropdown(
                    label="Account Type Priority",
                    choices=[
                        "no_preference",
                        "liquid_first",
                        "retirement_first",
                    ],
                    value=defaults["withdrawal_account_type_priority"],
                )
            with gr.Row():
                withdrawal_allocation_method = gr.Dropdown(
                    label="Within-Priority Allocation",
                    choices=["drain_one_then_next", "pro_rata"],
                    value=defaults["withdrawal_allocation_method"],
                )
                roth_handling_policy = gr.Dropdown(
                    label="Roth Handling",
                    choices=["last_resort", "normal_priority"],
                    value=defaults["roth_handling_policy"],
                )

        notes = gr.Textbox(label="Notes", value=defaults["notes"], lines=3)

        with gr.Accordion("People", open=True):
            people = gr.Dataframe(
                elem_id="people-table",
                elem_classes=["numeric-table"],
                headers=PEOPLE_HEADERS,
                datatype=[
                    "str", "str", "str", "number", "number", "number",
                    "number", "str", "number", "str", "bool",
                    "number", "str", "str", "bool", "str",
                ],
                value=defaults["people"],
                interactive=True,
            )

        with gr.Accordion("Buckets", open=False):
            buckets = gr.Dataframe(
                elem_id="buckets-table",
                elem_classes=["numeric-table"],
                headers=BUCKET_HEADERS,
                datatype=["str", "str", "str", "str", "number", "str", "str"],
                value=defaults["buckets"],
                interactive=True,
            )

        with gr.Accordion("Accounts", open=True):
            accounts = gr.Dataframe(
                elem_id="accounts-table",
                elem_classes=["numeric-table"],
                headers=ACCOUNT_HEADERS,
                datatype=[
                    "str", "str", "str", "str", "str", "str",
                    "str", "number", "str", "bool", "bool", "bool",
                ],
                value=defaults["accounts"],
                interactive=True,
            )

        with gr.Accordion("Cash Flows", open=True):
            cash_flows = gr.Dataframe(
                elem_id="cash-flows-table",
                elem_classes=["numeric-table"],
                headers=CASH_FLOW_HEADERS,
                datatype=[
                    "str", "str", "str", "str", "number",
                    "number", "number", "str", "str", "str",
                ],
                value=defaults["cash_flows"],
                interactive=True,
            )

        with gr.Accordion("Holdings", open=False):
            holdings = gr.Dataframe(
                elem_id="holdings-table",
                elem_classes=["numeric-table"],
                headers=HOLDING_HEADERS,
                datatype=[
                    "str", "str", "str", "str", "str",
                    "str", "str", "number", "str", "str",
                ],
                value=defaults["holdings"],
                interactive=True,
            )

        with gr.Accordion("Actual Balances", open=False):
            snapshots = gr.Dataframe(
                elem_id="snapshots-table",
                elem_classes=["numeric-table"],
                headers=SNAPSHOT_HEADERS,
                datatype=["str", "str", "str", "str", "str"],
                value=defaults["snapshots"],
                interactive=True,
            )

        gr.Markdown("## Forecast Output")
        forecast_summary = gr.Markdown("Run the forecast to see results.")
        forecast_table = gr.Dataframe(
            elem_id="forecast-table",
            elem_classes=["numeric-table"],
            headers=FORECAST_HEADERS,
            datatype=["number"] + (["str"] * (len(FORECAST_HEADERS) - 1)),
            interactive=False,
        )
        gr.Markdown("## Account Forecast")
        account_forecast_table = gr.Dataframe(
            elem_id="account-forecast-table",
            elem_classes=["numeric-table"],
            headers=ACCOUNT_FORECAST_HEADERS,
            datatype=[
                "number",
                "str",
                "str",
                "str",
                "number",
                "str",
                "str",
                "str",
                "str",
                "str",
                "str",
                "str",
                "str",
                "str",
                "str",
                "str",
            ],
            interactive=False,
        )
        report_markdown_state = gr.State("")
        with gr.Column(visible=False, elem_id="report-overlay") as report_overlay:
            with gr.Column(elem_id="report-modal-card"):
                with gr.Row():
                    gr.Markdown("## Forecast Report")
                    close_report_btn = gr.Button("Close", variant="secondary")
                report_popup_markdown = gr.Markdown()
                report_pdf_file = gr.File(
                    label="Forecast Report PDF",
                    interactive=False,
                )

        inputs = [
            plan_id,
            household_name,
            base_year,
            state,
            filing_status,
            tax_model,
            tax_projection_mode,
            projection_years,
            inflation_rate,
            default_bucket_expense_years,
            return_model_type,
            return_scenario_type,
            monte_carlo_simulations,
            monte_carlo_seed,
            monte_carlo_depletion_target_year,
            monte_carlo_depletion_target_age,
            bucket_return_short_term,
            bucket_return_intermediate,
            bucket_return_long_term,
            bucket_return_other,
            bucket_volatility_short_term,
            bucket_volatility_intermediate,
            bucket_volatility_long_term,
            bucket_volatility_other,
            planned_annual_spending,
            target_cash_reserve,
            federal_effective_tax_rate,
            state_effective_tax_rate,
            rmd_start_age,
            auto_fund_shortfall,
            use_withdrawal_priority_policy,
            withdrawal_tax_priority,
            withdrawal_owner_priority,
            withdrawal_account_type_priority,
            withdrawal_allocation_method,
            roth_handling_policy,
            hsa_contribution_limit_self,
            hsa_contribution_limit_family,
            hsa_catch_up_amount,
            notes,
            people,
            buckets,
            accounts,
            cash_flows,
            holdings,
            snapshots,
        ]

        ui_outputs = [
            plan_id,
            household_name,
            base_year,
            state,
            filing_status,
            tax_model,
            tax_projection_mode,
            projection_years,
            inflation_rate,
            default_bucket_expense_years,
            return_model_type,
            return_scenario_type,
            monte_carlo_simulations,
            monte_carlo_seed,
            monte_carlo_depletion_target_year,
            monte_carlo_depletion_target_age,
            bucket_return_short_term,
            bucket_return_intermediate,
            bucket_return_long_term,
            bucket_return_other,
            bucket_volatility_short_term,
            bucket_volatility_intermediate,
            bucket_volatility_long_term,
            bucket_volatility_other,
            planned_annual_spending,
            target_cash_reserve,
            federal_effective_tax_rate,
            state_effective_tax_rate,
            rmd_start_age,
            auto_fund_shortfall,
            use_withdrawal_priority_policy,
            withdrawal_tax_priority,
            withdrawal_owner_priority,
            withdrawal_account_type_priority,
            withdrawal_allocation_method,
            roth_handling_policy,
            hsa_contribution_limit_self,
            hsa_contribution_limit_family,
            hsa_catch_up_amount,
            notes,
            people,
            buckets,
            accounts,
            cash_flows,
            holdings,
            snapshots,
            status,
            imported_workbook_path,
        ]

        load_sample_btn.click(
            fn=load_sample_case,
            inputs=[sample_selector],
            outputs=ui_outputs,
        )
        workbook_input.change(
            fn=load_workbook_case,
            inputs=[workbook_input],
            outputs=ui_outputs,
        )
        run_forecast_btn.click(
            fn=run_forecast_ui,
            inputs=inputs,
            outputs=[
                forecast_table,
                account_forecast_table,
                forecast_summary,
                status,
                report_markdown_state,
                report_popup_markdown,
                report_pdf_file,
                view_report_btn,
            ],
        )
        export_btn.click(
            fn=export_workbook_ui,
            inputs=inputs + [export_mode, export_directory, imported_workbook_path],
            outputs=[export_file, status],
        )
        view_report_btn.click(
            fn=open_report_popup,
            inputs=[report_markdown_state],
            outputs=[report_overlay, report_popup_markdown],
        )
        close_report_btn.click(
            fn=close_report_popup,
            outputs=[report_overlay],
        )

    return demo


def load_sample_case(sample_name: str):
    values = plan_to_ui_values(sample_plan(sample_name))
    return _ui_output_tuple(
        values,
        f"Loaded sample case: `{sample_name or DEFAULT_SAMPLE_NAME}`.",
        None,
    )


def load_workbook_case(path: str | None):
    if not path:
        return _ui_output_tuple(
            plan_to_ui_values(sample_plan()),
            "No workbook selected.",
            None,
        )
    try:
        values = import_plan_to_ui(path)
        return _ui_output_tuple(values, f"Imported workbook: `{path}`", path)
    except Exception as exc:
        sample = plan_to_ui_values(sample_plan())
        return _ui_output_tuple(sample, f"Import failed: `{exc}`", None)


def run_forecast_ui(*args):
    try:
        plan = ui_values_to_plan(UIPlanPayload.from_ordered_values(args))
        table, account_table, summary, report_markdown, report_pdf_path = forecast_with_report_for_ui(plan)
        return (
            table,
            account_table,
            summary,
            f"Forecast completed successfully.\n\nReport saved to `{report_pdf_path}`",
            report_markdown,
            report_markdown,
            report_pdf_path,
            gr.update(interactive=True),
        )
    except Exception as exc:
        return (
            [],
            [],
            f"Forecast failed.\n\n`{exc}`",
            f"Forecast failed: `{exc}`",
            "",
            "",
            None,
            gr.update(interactive=False),
        )


def export_workbook_ui(*args):
    try:
        export_mode = args[-3]
        export_directory = args[-2]
        imported_workbook_path = args[-1]
        plan = ui_values_to_plan(UIPlanPayload.from_ordered_values(args[:-3]))
        path = export_plan_for_ui(
            plan,
            export_mode=export_mode or EXPORT_MODE_NEW_FILE,
            export_directory=export_directory or DEFAULT_EXPORT_DIRECTORY,
            imported_workbook_path=imported_workbook_path,
        )
        return gr.update(value=path, visible=True), f"Workbook exported to `{path}`"
    except Exception as exc:
        return gr.update(value=None, visible=False), f"Export failed: `{exc}`"


def open_report_popup(markdown: str):
    if not markdown:
        return gr.update(visible=False), "Run the forecast to generate a report."
    return gr.update(visible=True), markdown


def close_report_popup():
    return gr.update(visible=False)


def _ui_output_tuple(values: dict[str, object], status_message: str, imported_path: str | None):
    return (
        values["plan_id"],
        values["household_name"],
        values["base_year"],
        values["state"],
        values["filing_status"],
        values["tax_model"],
        values["tax_projection_mode"],
        values["projection_years"],
        values["inflation_rate"],
        values["default_bucket_expense_years"],
        values["return_model_type"],
        values["return_scenario_type"],
        values["monte_carlo_simulations"],
        values["monte_carlo_seed"],
        values["monte_carlo_depletion_target_year"],
        values["monte_carlo_depletion_target_age"],
        values["bucket_return_short_term"],
        values["bucket_return_intermediate"],
        values["bucket_return_long_term"],
        values["bucket_return_other"],
        values["bucket_volatility_short_term"],
        values["bucket_volatility_intermediate"],
        values["bucket_volatility_long_term"],
        values["bucket_volatility_other"],
        values["planned_annual_spending"],
        values["target_cash_reserve"],
        values["federal_effective_tax_rate"],
        values["state_effective_tax_rate"],
        values["rmd_start_age"],
        values["auto_fund_shortfall"],
        values["use_withdrawal_priority_policy"],
        values["withdrawal_tax_priority"],
        values["withdrawal_owner_priority"],
        values["withdrawal_account_type_priority"],
        values["withdrawal_allocation_method"],
        values["roth_handling_policy"],
        values["hsa_contribution_limit_self"],
        values["hsa_contribution_limit_family"],
        values["hsa_catch_up_amount"],
        values["notes"],
        values["people"],
        values["buckets"],
        values["accounts"],
        values["cash_flows"],
        values["holdings"],
        values["snapshots"],
        status_message,
        imported_path,
    )


if __name__ == "__main__":
    build_ui().launch(css=CSS, theme=mojave_sage_theme())
