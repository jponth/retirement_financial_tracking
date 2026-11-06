from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
import re
import tempfile

from fpdf import FPDF

import retirement_financial_tracking.io.workbook as workbook_io
from retirement_financial_tracking.domain.models import (
    ForecastResult,
    HouseholdPlan,
    TaxTreatment,
)


@dataclass(frozen=True, slots=True)
class ReportTable:
    headers: list[str]
    rows: list[list[object]]


@dataclass(frozen=True, slots=True)
class ReportSection:
    title: str
    lines: list[str] = field(default_factory=list)
    table: ReportTable | None = None


@dataclass(frozen=True, slots=True)
class ForecastReport:
    title: str
    subtitle: str
    prepared_on: str
    sections: list[ReportSection]
    disclaimer: str


def build_forecast_report(
    plan: HouseholdPlan,
    forecast: ForecastResult,
    *,
    generated_on: str | None = None,
    source_workbook_name: str = "",
) -> ForecastReport:
    generated_on = generated_on or datetime.now().strftime("%d-%b-%Y %I:%M:%S %p")
    start_year = forecast.rows[0].year if forecast.rows else plan.base_year
    end_year = forecast.rows[-1].year if forecast.rows else plan.base_year
    sections = [
        ReportSection(
            title="Executive Summary",
            lines=workbook_io._build_headline_summary_blob(plan, forecast).splitlines(),
        ),
        ReportSection(
            title="Key Assumptions",
            lines=workbook_io._build_key_assumptions_blob(plan).splitlines(),
        ),
        ReportSection(
            title="Key Warnings / Observations",
            lines=_normalize_warning_lines(
                workbook_io._build_warnings_blob(plan, forecast).splitlines()
            ),
        ),
        ReportSection(
            title="Next 5 Years Preview",
            table=_format_table(
                *workbook_io._build_next_five_years_preview(plan, forecast),
                currency_columns=set(range(1, 10)),
            ),
        ),
        ReportSection(
            title="Recommended Actions",
            table=ReportTable(*workbook_io._build_recommended_actions(plan, forecast)),
        ),
        ReportSection(
            title="Annual Cash Flow and Taxes",
            table=_build_cash_flow_table(forecast),
        ),
        ReportSection(
            title="Annual Account Balances",
            table=_build_account_balances_table(plan, forecast),
        ),
        ReportSection(
            title="Annual Balances by Bucket",
            table=_build_bucket_balances_table(plan, forecast),
        ),
        ReportSection(
            title="Run Metadata",
            lines=workbook_io._build_run_metadata_blob(
                plan=plan,
                forecast=forecast,
                generated_on=generated_on,
                source_workbook_name=source_workbook_name,
            ).splitlines(),
        ),
        ReportSection(
            title="Modeling Limitations",
            lines=_build_modeling_limitations(plan),
        ),
    ]
    return ForecastReport(
        title="Retirement Forecast Report",
        subtitle=f"Account-by-account projection for {start_year}-{end_year}",
        prepared_on=generated_on,
        sections=sections,
        disclaimer=(
            "Planning projection only. Not individualized tax, legal, Social Security, "
            "health insurance, or investment advice."
        ),
    )


def render_report_markdown(report: ForecastReport) -> str:
    lines = [
        f"# {report.title}",
        "",
        report.subtitle,
        "",
        f"Prepared: {report.prepared_on}",
        "",
    ]
    for index, section in enumerate(report.sections, start=1):
        lines.append(f"## {index}. {section.title}")
        lines.append("")
        if section.lines:
            lines.extend(f"- {line}" for line in section.lines)
            lines.append("")
        if section.table is not None:
            lines.extend(_render_markdown_table(section.table))
            lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(report.disclaimer)
    return "\n".join(lines).strip()


def export_report_pdf(
    report: ForecastReport,
    *,
    output_path: str | Path,
) -> Path:
    pdf = FPDF(orientation="L", unit="mm", format="Letter")
    pdf.set_auto_page_break(auto=True, margin=12)
    pdf.add_page()
    pdf.set_title(report.title)
    pdf.set_author("retirement_financial_tracking")

    pdf.set_font("Helvetica", "B", 18)
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(0, 10, report.title)
    pdf.ln(1)
    pdf.set_font("Helvetica", "", 11)
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(0, 7, report.subtitle)
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(0, 7, f"Prepared: {report.prepared_on}")
    pdf.ln(2)

    for index, section in enumerate(report.sections, start=1):
        pdf.set_font("Helvetica", "B", 13)
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(0, 8, f"{index}. {section.title}")
        pdf.ln(1)
        if section.lines:
            pdf.set_font("Helvetica", "", 10)
            for line in section.lines:
                pdf.set_x(pdf.l_margin)
                pdf.multi_cell(0, 6, f"- {line}")
            pdf.ln(1)
        if section.table is not None:
            _write_pdf_table(pdf, section.table)
            pdf.ln(3)

    pdf.set_font("Helvetica", "I", 9)
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(0, 6, report.disclaimer)

    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(destination))
    return destination


def generate_report_assets(
    plan: HouseholdPlan,
    forecast: ForecastResult,
    *,
    source_workbook_name: str = "",
    output_directory: str | Path | None = None,
) -> tuple[ForecastReport, str, str]:
    timestamp = datetime.now().strftime("%d-%b-%Y %I:%M:%S %p")
    report = build_forecast_report(
        plan,
        forecast,
        generated_on=timestamp,
        source_workbook_name=source_workbook_name,
    )
    markdown = render_report_markdown(report)
    report_directory = Path(output_directory) if output_directory else _transient_report_directory()
    pdf_path = export_report_pdf(
        report,
        output_path=report_directory / _report_filename(plan, timestamp),
    )
    return report, markdown, str(pdf_path)


def _build_cash_flow_table(forecast: ForecastResult) -> ReportTable:
    headers = [
        "Year",
        "Income",
        "Social Security",
        "Expenses",
        "Taxes",
        "Withdrawals",
        "RMD",
        "End Assets",
    ]
    rows = [
        [
            row.year,
            _format_currency(row.income_total),
            _format_currency(row.social_security_total),
            _format_currency(row.expense_total),
            _format_currency(row.tax_total),
            _format_currency(row.withdrawal_total),
            _format_currency(row.rmd_withdrawal_total),
            _format_currency(row.total_ending_assets),
        ]
        for row in forecast.rows
    ]
    return ReportTable(headers=headers, rows=rows)


def _build_account_balances_table(
    plan: HouseholdPlan,
    forecast: ForecastResult,
) -> ReportTable:
    account_names = [account.account_name for account in plan.accounts]
    headers = ["Year", *account_names, "Taxable Total", "Pretax Total", "Tax-Free Total", "Total Portfolio"]
    rows: list[list[object]] = []
    for year in sorted({row.year for row in forecast.account_rows}):
        rows_by_account_name = {
            row.account_name: row
            for row in forecast.account_rows
            if row.year == year
        }
        taxable_total = Decimal("0.00")
        pretax_total = Decimal("0.00")
        tax_free_total = Decimal("0.00")
        for account in plan.accounts:
            row = rows_by_account_name.get(account.account_name)
            if row is None:
                continue
            if account.tax_treatment is TaxTreatment.TAXABLE:
                taxable_total += row.end_balance
            elif account.tax_treatment is TaxTreatment.TAX_DEFERRED:
                pretax_total += row.end_balance
            else:
                tax_free_total += row.end_balance
        total_portfolio = taxable_total + pretax_total + tax_free_total
        rows.append(
            [
                year,
                *[
                    _format_currency(
                        rows_by_account_name.get(account_name).end_balance
                        if rows_by_account_name.get(account_name) is not None
                        else Decimal("0.00")
                    )
                    for account_name in account_names
                ],
                _format_currency(taxable_total),
                _format_currency(pretax_total),
                _format_currency(tax_free_total),
                _format_currency(total_portfolio),
            ]
        )
    return ReportTable(headers=headers, rows=rows)


def _build_bucket_balances_table(
    plan: HouseholdPlan,
    forecast: ForecastResult,
) -> ReportTable:
    bucket_headers = [bucket.bucket_name for bucket in plan.buckets]
    headers = ["Year", *bucket_headers, "Total"]
    balances_by_year = workbook_io._bucket_balances_by_year(plan, forecast)
    rows: list[list[object]] = []
    for year in sorted({row.year for row in forecast.rows}):
        bucket_values = [
            balances_by_year.get(year, {}).get(bucket.bucket_id, Decimal("0.00"))
            for bucket in plan.buckets
        ]
        rows.append(
            [
                year,
                *[_format_currency(value) for value in bucket_values],
                _format_currency(sum(bucket_values, start=Decimal("0.00"))),
            ]
        )
    return ReportTable(headers=headers, rows=rows)


def _build_modeling_limitations(plan: HouseholdPlan) -> list[str]:
    lines = [
        "Forecast results are planning estimates based on the current workbook inputs and assumptions.",
        "Actual returns, expenses, taxes, and withdrawal timing will differ from the modeled path.",
        "Bracket-based tax mode currently models federal ordinary-income brackets plus Connecticut ordinary-income tax, but not Social Security taxation, capital gains, credits, AMT, or IRMAA.",
        "Future tax law changes are not automatically projected beyond the selected tax model and inflation mode.",
        "Forecast accuracy depends on keeping Actual Balances up to date and revisiting assumptions regularly.",
    ]
    if plan.settings.return_model_type.name == "MONTE_CARLO":
        lines.append("Monte Carlo output is a modeled range, not a prediction of actual market results.")
    return lines


def _normalize_warning_lines(lines: list[str]) -> list[str]:
    return [line.removeprefix("- ").strip() for line in lines if line.strip()]


def _format_table(
    headers: list[str],
    rows: list[list[object]],
    *,
    currency_columns: set[int],
) -> ReportTable:
    formatted_rows: list[list[object]] = []
    for row in rows:
        formatted_row: list[object] = []
        for index, value in enumerate(row):
            if index == 0:
                formatted_row.append(value)
            elif index in currency_columns:
                formatted_row.append(_format_currency(value))
            else:
                formatted_row.append(value)
        formatted_rows.append(formatted_row)
    return ReportTable(headers=headers, rows=formatted_rows)


def _format_currency(value: Decimal | int | float) -> str:
    rounded = Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return f"${int(rounded):,}"


def _render_markdown_table(table: ReportTable) -> list[str]:
    lines = [
        "| " + " | ".join(table.headers) + " |",
        "| " + " | ".join(["---"] * len(table.headers)) + " |",
    ]
    for row in table.rows:
        lines.append("| " + " | ".join(str(value) for value in row) + " |")
    return lines


def _write_pdf_table(pdf: FPDF, table: ReportTable) -> None:
    available_width = pdf.w - pdf.l_margin - pdf.r_margin
    raw_widths = [max(len(str(header)), 10) for header in table.headers]
    for row in table.rows[: min(len(table.rows), 10)]:
        for index, value in enumerate(row):
            raw_widths[index] = max(raw_widths[index], min(len(str(value)), 28))
    total_raw_width = sum(raw_widths)
    widths = [(width / total_raw_width) * available_width for width in raw_widths]

    header_font_size = 8 if len(table.headers) > 8 else 9
    body_font_size = 7 if len(table.headers) > 8 else 8

    pdf.set_font("Helvetica", "B", header_font_size)
    for header, width in zip(table.headers, widths, strict=True):
        pdf.cell(width, 7, str(header), border=1, align="C")
    pdf.ln()

    pdf.set_font("Helvetica", "", body_font_size)
    for row in table.rows:
        for value, width in zip(row, widths, strict=True):
            pdf.cell(width, 6, str(value), border=1, align="C")
        pdf.ln()


def _report_filename(plan: HouseholdPlan, timestamp: str) -> str:
    slug = _slugify(plan.household_name or plan.plan_id or "forecast-report")
    compact_timestamp = datetime.strptime(timestamp, "%d-%b-%Y %I:%M:%S %p").strftime("%d-%b-%y-%H%M%S")
    return f"{slug}_forecast_report_{compact_timestamp}.pdf"


def _transient_report_directory() -> Path:
    directory = Path(tempfile.gettempdir()) / "retirement_financial_tracking_downloads"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_") or "forecast_report"
