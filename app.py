from __future__ import annotations

from pathlib import Path

import gradio as gr

from retirement_financial_tracking import load_app_metadata
from retirement_financial_tracking.ui_theme import (
    SAGE_PANEL_BACKGROUND,
    SAGE_PANEL_BORDER,
    SAGE_PANEL_SHADOW,
    SAGE_RAIL_BACKGROUND,
    SAGE_RAIL_BORDER,
    mojave_sage_theme,
)
from retirement_financial_tracking.ui_helpers import (
    DEFAULT_EXPORT_DIRECTORY,
    DEFAULT_SAMPLE_NAME,
    EXPORT_MODE_NEW_FILE,
    EXPORT_MODE_SAVE_UPDATED_COPY,
    EXPORT_MODE_UPDATE_IMPORTED_WORKBOOK,
    PLAN_UI_INPUT_KEYS,
    UIPlanPayload,
    export_plan_for_ui,
    forecast_with_report_for_ui,
    import_plan_to_ui,
    plan_to_ui_values,
    sample_plan,
    sample_plan_names,
    ui_values_to_plan,
)
from simple_spa_app import (
    ACCOUNT_FORECAST_HEADERS,
    ACCOUNT_HEADERS,
    BUCKET_HEADERS,
    CASH_FLOW_HEADERS,
    CSS as SIMPLE_SPA_CSS,
    FORECAST_HEADERS,
    HOLDING_HEADERS,
    PEOPLE_HEADERS,
    SNAPSHOT_HEADERS,
)


CSS = (
    SIMPLE_SPA_CSS
    + f"""
    #workspace-shell {{
        gap: 1.5rem;
    }}

    #workspace-shell > .gr-column:first-child {{
        min-width: 0;
    }}

    #summary-rail {{
        background: {SAGE_RAIL_BACKGROUND};
        border: 1px solid {SAGE_RAIL_BORDER};
        border-radius: 18px;
        padding: 1.1rem;
        box-shadow: 0 12px 28px {SAGE_PANEL_SHADOW};
    }}

    #summary-rail h3 {{
        margin-bottom: 0.5rem;
    }}

    #summary-rail p,
    #summary-rail li {{
        color: #46412F;
    }}

    #report-panel,
    #forecast-panel,
    #export-panel,
    #case-setup-panel {{
        border: 1px solid {SAGE_PANEL_BORDER};
        border-radius: 18px;
        padding: 1.1rem;
        background: {SAGE_PANEL_BACKGROUND};
        box-shadow: 0 14px 30px {SAGE_PANEL_SHADOW};
    }}

    #report-panel .tab-nav,
    #forecast-panel .tab-nav,
    #case-setup-panel .tab-nav {{
        background: rgba(255, 250, 241, 0.82);
    }}

    #workspace-shell .gr-button {{
        box-shadow: 0 3px 10px rgba(70, 65, 47, 0.08);
    }}
"""
)


def run_forecast_ui(*args):
    try:
        plan = ui_values_to_plan(UIPlanPayload.from_ordered_values(args))
        table, account_table, summary, report_markdown, report_pdf_path = forecast_with_report_for_ui(
            plan
        )
        return (
            table,
            account_table,
            summary,
            f"Forecast completed successfully.\n\nReport saved to `{report_pdf_path}`",
            report_markdown,
            report_pdf_path,
        )
    except Exception as exc:
        return (
            [],
            [],
            f"Forecast failed.\n\n`{exc}`",
            f"Forecast failed: `{exc}`",
            "",
            None,
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
        return gr.update(value=path, visible=True), f"Workbook exported to `{path}`", path
    except Exception as exc:
        return gr.update(value=None, visible=False), f"Export failed: `{exc}`", None


def build_ui() -> gr.Blocks:
    metadata = load_app_metadata()
    defaults = plan_to_ui_values(sample_plan())
    default_report_message = (
        "Run the forecast from the Forecast tab to generate a presentable report here."
    )

    with gr.Blocks(title=metadata.product_display_name) as demo:
        gr.Markdown(f"# {metadata.product_display_name}")
        gr.Markdown(
            "An application to support financial forecasting, tracking and plan actions. "
            "This application does not store any information on its servers. You're responsible "
            "to export the output (an Excel file), after you have performed the forecasting. "
            "You take 100% responsibility of your financial matters and the no one else is responsible."
        )

        status = gr.Markdown("Ready.")
        imported_workbook_path = gr.State(value=None)
        latest_report_path = gr.State(value=None)
        latest_export_path = gr.State(value=None)
        latest_forecast_summary = gr.State(value="")

        with gr.Row(elem_id="workspace-shell", equal_height=False):
            with gr.Column(scale=7):
                with gr.Tabs():
                    with gr.Tab("Case Setup"):
                        with gr.Column(elem_id="case-setup-panel"):
                            with gr.Row():
                                sample_selector = gr.Dropdown(
                                    label="Sample Case",
                                    choices=sample_plan_names(),
                                    value=DEFAULT_SAMPLE_NAME,
                                )
                                load_sample_btn = gr.Button(
                                    "Load Sample Case",
                                    variant="secondary",
                                )
                                workbook_input = gr.File(label="Import Workbook", type="filepath")

                            with gr.Tabs():
                                with gr.Tab("Household"):
                                    with gr.Row():
                                        plan_id = gr.Textbox(
                                            label="Plan ID",
                                            value=defaults["plan_id"],
                                        )
                                        household_name = gr.Textbox(
                                            label="Household Name",
                                            value=defaults["household_name"],
                                        )
                                        base_year = gr.Number(
                                            label="Base Year",
                                            value=defaults["base_year"],
                                            precision=0,
                                        )

                                    with gr.Row():
                                        state = gr.Textbox(
                                            label="State",
                                            value=defaults["state"],
                                        )
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
                                        planned_annual_spending = gr.Number(
                                            label="Planned Annual Spending",
                                            value=defaults["planned_annual_spending"],
                                        )
                                        target_cash_reserve = gr.Number(
                                            label="Target Cash Reserve",
                                            value=defaults["target_cash_reserve"],
                                        )
                                        rmd_start_age = gr.Number(
                                            label="RMD Start Age",
                                            value=defaults["rmd_start_age"],
                                            precision=0,
                                        )

                                    notes = gr.Textbox(
                                        label="Notes",
                                        value=defaults["notes"],
                                        lines=4,
                                    )

                                with gr.Tab("Tax & Forecast Rules"):
                                    with gr.Row():
                                        inflation_rate = gr.Number(
                                            label="Inflation Rate",
                                            value=defaults["inflation_rate"],
                                        )
                                        default_bucket_expense_years = gr.Number(
                                            label="Default Bucket Expense Years",
                                            value=defaults["default_bucket_expense_years"],
                                        )
                                        auto_fund_shortfall = gr.Checkbox(
                                            label="Auto-Fund Shortfall",
                                            value=defaults["auto_fund_shortfall"],
                                        )

                                    with gr.Row():
                                        return_model_type = gr.Dropdown(
                                            label="Return Model",
                                            choices=["simple", "scenario_based", "monte_carlo"],
                                            value=defaults["return_model_type"],
                                        )
                                        return_scenario_type = gr.Dropdown(
                                            label="Return Scenario",
                                            choices=[
                                                "base",
                                                "conservative",
                                                "optimistic",
                                                "bad_first_5_years",
                                            ],
                                            value=defaults["return_scenario_type"],
                                        )
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
                                        "Use `scenario_based` for deterministic year-by-year scenarios. "
                                        "Use `monte_carlo` for randomized yearly bucket returns based on "
                                        "the return and volatility settings."
                                    )

                                    with gr.Row():
                                        federal_effective_tax_rate = gr.Number(
                                            label="Federal Effective Tax Rate",
                                            value=defaults["federal_effective_tax_rate"],
                                        )
                                        state_effective_tax_rate = gr.Number(
                                            label="State Effective Tax Rate",
                                            value=defaults["state_effective_tax_rate"],
                                        )
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
                                            "Bucket draw order remains fixed as "
                                            "`short_term -> intermediate -> long_term -> other`. "
                                            "These settings choose which accounts get used inside each bucket."
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
                                                value=defaults[
                                                    "withdrawal_account_type_priority"
                                                ],
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

                                with gr.Tab("People"):
                                    people = gr.Dataframe(
                                        elem_id="people-table",
                                        elem_classes=["numeric-table"],
                                        headers=PEOPLE_HEADERS,
                                        datatype=[
                                            "str",
                                            "str",
                                            "str",
                                            "number",
                                            "number",
                                            "number",
                                            "number",
                                            "str",
                                            "number",
                                            "str",
                                            "bool",
                                            "number",
                                            "str",
                                            "str",
                                            "bool",
                                            "str",
                                        ],
                                        value=defaults["people"],
                                        interactive=True,
                                    )

                                with gr.Tab("Accounts"):
                                    accounts = gr.Dataframe(
                                        elem_id="accounts-table",
                                        elem_classes=["numeric-table"],
                                        headers=ACCOUNT_HEADERS,
                                        datatype=[
                                            "str",
                                            "str",
                                            "str",
                                            "str",
                                            "str",
                                            "str",
                                            "str",
                                            "number",
                                            "str",
                                            "bool",
                                            "bool",
                                            "bool",
                                        ],
                                        value=defaults["accounts"],
                                        interactive=True,
                                    )

                                with gr.Tab("Buckets"):
                                    buckets = gr.Dataframe(
                                        elem_id="buckets-table",
                                        elem_classes=["numeric-table"],
                                        headers=BUCKET_HEADERS,
                                        datatype=[
                                            "str",
                                            "str",
                                            "str",
                                            "str",
                                            "number",
                                            "str",
                                            "str",
                                        ],
                                        value=defaults["buckets"],
                                        interactive=True,
                                    )

                                with gr.Tab("Cash Flows"):
                                    cash_flows = gr.Dataframe(
                                        elem_id="cash-flows-table",
                                        elem_classes=["numeric-table"],
                                        headers=CASH_FLOW_HEADERS,
                                        datatype=[
                                            "str",
                                            "str",
                                            "str",
                                            "str",
                                            "number",
                                            "number",
                                            "number",
                                            "str",
                                            "str",
                                            "str",
                                        ],
                                        value=defaults["cash_flows"],
                                        interactive=True,
                                    )

                                with gr.Tab("Holdings"):
                                    holdings = gr.Dataframe(
                                        elem_id="holdings-table",
                                        elem_classes=["numeric-table"],
                                        headers=HOLDING_HEADERS,
                                        datatype=[
                                            "str",
                                            "str",
                                            "str",
                                            "str",
                                            "str",
                                            "str",
                                            "str",
                                            "number",
                                            "str",
                                            "str",
                                        ],
                                        value=defaults["holdings"],
                                        interactive=True,
                                    )

                                with gr.Tab("Actual Balances"):
                                    snapshots = gr.Dataframe(
                                        elem_id="snapshots-table",
                                        elem_classes=["numeric-table"],
                                        headers=SNAPSHOT_HEADERS,
                                        datatype=["str", "str", "str", "str", "str"],
                                        value=defaults["snapshots"],
                                        interactive=True,
                                    )

                    with gr.Tab("Forecast"):
                        with gr.Column(elem_id="forecast-panel"):
                            gr.Markdown(
                                "Run a forecast snapshot from the current case inputs. "
                                "The results shown here feed the Report and Export tabs."
                            )
                            run_forecast_btn = gr.Button("Run Forecast", variant="primary")
                            forecast_summary = gr.Markdown(
                                "Run the forecast to see results."
                            )
                            with gr.Tabs():
                                with gr.Tab("Household Forecast"):
                                    forecast_table = gr.Dataframe(
                                        elem_id="forecast-table",
                                        elem_classes=["numeric-table"],
                                        headers=FORECAST_HEADERS,
                                        datatype=["number"]
                                        + (["str"] * (len(FORECAST_HEADERS) - 1)),
                                        interactive=False,
                                    )
                                with gr.Tab("Account Forecast"):
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

                    with gr.Tab("Report"):
                        with gr.Column(elem_id="report-panel"):
                            gr.Markdown(
                                "The report is generated from the latest successful forecast run."
                            )
                            report_markdown = gr.Markdown(default_report_message)
                            report_pdf_file = gr.File(
                                label="Forecast Report PDF",
                                interactive=False,
                            )

                    with gr.Tab("Export"):
                        with gr.Column(elem_id="export-panel"):
                            gr.Markdown(
                                "Export the current case workbook, preserving imported workbook formatting "
                                "where possible and appending timestamped forecast tabs."
                            )
                            with gr.Row():
                                export_mode = gr.Dropdown(
                                    label="Export Mode",
                                    choices=[
                                        EXPORT_MODE_SAVE_UPDATED_COPY,
                                        EXPORT_MODE_UPDATE_IMPORTED_WORKBOOK,
                                        EXPORT_MODE_NEW_FILE,
                                    ],
                                    value=EXPORT_MODE_SAVE_UPDATED_COPY,
                                )
                                export_directory = gr.Textbox(
                                    label="Target Export Folder",
                                    value=DEFAULT_EXPORT_DIRECTORY,
                                )
                            export_btn = gr.Button(
                                "Export Workbook",
                                variant="secondary",
                            )
                            export_file = gr.File(
                                label="Exported Workbook",
                                visible=False,
                            )

            with gr.Column(scale=3):
                with gr.Column(elem_id="summary-rail"):
                    gr.Markdown("### Current Case Snapshot")
                    case_snapshot = gr.Markdown(
                        _summary_rail_markdown(
                            defaults,
                            imported_path=None,
                            forecast_summary="",
                            report_pdf_path=None,
                            export_path=None,
                        )
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
            case_snapshot,
            forecast_table,
            account_forecast_table,
            forecast_summary,
            report_markdown,
            report_pdf_file,
            latest_report_path,
            latest_export_path,
            latest_forecast_summary,
            export_file,
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
            fn=run_forecast_workspace_ui,
            inputs=inputs + [imported_workbook_path, latest_export_path],
            outputs=[
                forecast_table,
                account_forecast_table,
                forecast_summary,
                report_markdown,
                report_pdf_file,
                status,
                case_snapshot,
                latest_report_path,
                latest_forecast_summary,
            ],
        )
        export_btn.click(
            fn=export_workbook_workspace_ui,
            inputs=inputs
            + [
                export_mode,
                export_directory,
                imported_workbook_path,
                latest_forecast_summary,
                latest_report_path,
            ],
            outputs=[
                export_file,
                status,
                case_snapshot,
                latest_export_path,
            ],
        )

    return demo


def load_sample_case(sample_name: str):
    values = plan_to_ui_values(sample_plan(sample_name))
    return _workspace_output_tuple(
        values,
        status_message=f"Loaded sample case: `{sample_name or DEFAULT_SAMPLE_NAME}`.",
        imported_path=None,
    )


def load_workbook_case(path: str | None):
    if not path:
        return _workspace_output_tuple(
            plan_to_ui_values(sample_plan()),
            status_message="No workbook selected.",
            imported_path=None,
        )

    try:
        values = import_plan_to_ui(path)
        return _workspace_output_tuple(
            values,
            status_message=f"Imported workbook: `{path}`",
            imported_path=path,
        )
    except Exception as exc:
        return _workspace_output_tuple(
            plan_to_ui_values(sample_plan()),
            status_message=f"Import failed: `{exc}`",
            imported_path=None,
        )


def run_forecast_workspace_ui(*args):
    plan_args = args[: len(PLAN_UI_INPUT_KEYS)]
    imported_path = args[-2]
    export_path = args[-1]
    values = UIPlanPayload.from_ordered_values(plan_args).as_dict()

    (
        forecast_table,
        account_forecast_table,
        forecast_summary,
        status_message,
        report_markdown,
        report_pdf_path,
    ) = run_forecast_ui(*plan_args)

    case_snapshot = _summary_rail_markdown(
        values,
        imported_path=imported_path,
        forecast_summary=forecast_summary if report_markdown else "",
        report_pdf_path=report_pdf_path,
        export_path=export_path,
    )

    return (
        forecast_table,
        account_forecast_table,
        forecast_summary,
        report_markdown or "Run the forecast to generate a report here.",
        report_pdf_path,
        status_message,
        case_snapshot,
        report_pdf_path,
        forecast_summary if report_markdown else "",
    )


def export_workbook_workspace_ui(*args):
    plan_args = args[: len(PLAN_UI_INPUT_KEYS)]
    export_mode = args[len(PLAN_UI_INPUT_KEYS)]
    export_directory = args[len(PLAN_UI_INPUT_KEYS) + 1]
    imported_path = args[len(PLAN_UI_INPUT_KEYS) + 2]
    forecast_summary = args[len(PLAN_UI_INPUT_KEYS) + 3]
    report_pdf_path = args[len(PLAN_UI_INPUT_KEYS) + 4]

    values = UIPlanPayload.from_ordered_values(plan_args).as_dict()
    export_file_update, status_message, export_path = export_workbook_ui(
        *plan_args,
        export_mode,
        export_directory,
        imported_path,
    )
    case_snapshot = _summary_rail_markdown(
        values,
        imported_path=imported_path,
        forecast_summary=forecast_summary,
        report_pdf_path=report_pdf_path,
        export_path=export_path,
    )
    return export_file_update, status_message, case_snapshot, export_path


def _workspace_output_tuple(
    values: dict[str, object],
    *,
    status_message: str,
    imported_path: str | None,
):
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
        _summary_rail_markdown(
            values,
            imported_path=imported_path,
            forecast_summary="",
            report_pdf_path=None,
            export_path=None,
        ),
        [],
        [],
        "Run the forecast to see results.",
        "Run the forecast from the Forecast tab to generate a presentable report here.",
        None,
        None,
        None,
        "",
        gr.update(value=None, visible=False),
    )


def _summary_rail_markdown(
    values: dict[str, object],
    *,
    imported_path: str | None,
    forecast_summary: str,
    report_pdf_path: str | None,
    export_path: str | None,
) -> str:
    summary_lines = [
        f"- **Household:** {values['household_name']}",
        f"- **Plan ID:** `{values['plan_id']}`",
        f"- **Base Year:** {values['base_year']}",
        f"- **Projection Years:** {values['projection_years']}",
        f"- **Tax Model:** `{values['tax_model']}`",
        f"- **Return Model:** `{values['return_model_type']}`",
    ]

    if imported_path:
        summary_lines.append(f"- **Imported Workbook:** `{Path(imported_path).name}`")

    if report_pdf_path:
        summary_lines.append(f"- **Latest Report PDF:** `{Path(report_pdf_path).name}`")

    if export_path:
        summary_lines.append(f"- **Latest Export:** `{Path(export_path).name}`")

    forecast_block = "No forecast run yet."
    if forecast_summary:
        forecast_lines = [line for line in forecast_summary.splitlines() if line.strip()]
        forecast_block = "\n".join(f"- {line}" for line in forecast_lines[:6])

    return (
        "#### Case\n"
        + "\n".join(summary_lines)
        + "\n\n#### Latest Forecast\n"
        + forecast_block
        + "\n\n#### Workflow\n"
        + "- Edit inputs in **Case Setup**.\n"
        + "- Run a snapshot in **Forecast**.\n"
        + "- Review the narrative in **Report**.\n"
        + "- Save workbook outputs from **Export**."
    )


if __name__ == "__main__":
    build_ui().launch(css=CSS, theme=mojave_sage_theme())
