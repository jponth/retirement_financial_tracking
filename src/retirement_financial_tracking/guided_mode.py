from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import logging
import re
from typing import Any

from retirement_financial_tracking.llm_client import generate, provider_status_text
from retirement_financial_tracking.ui_helpers import (
    export_plan_for_ui,
    forecast_with_report_for_ui,
    plan_to_ui_values,
    sample_plan,
    ui_values_to_plan,
)

LOGGER = logging.getLogger(__name__)


GUIDED_FIELDS = [
    {
        "key": "household_name",
        "label": "household name",
        "question": "What should I call this retirement plan?",
        "type": "text",
    },
    {
        "key": "state",
        "label": "state",
        "question": "Which state should I use for taxes? A two-letter state like CT is perfect.",
        "type": "state",
    },
    {
        "key": "base_year",
        "label": "base year",
        "question": "What year should the forecast start? If you're unsure, just say this year.",
        "type": "int",
        "default": datetime.now().year,
    },
    {
        "key": "current_age",
        "label": "current age",
        "question": "How old is the primary person today?",
        "type": "int",
    },
    {
        "key": "retirement_age",
        "label": "retirement age",
        "question": "At what age does the primary person expect to retire?",
        "type": "int",
    },
    {
        "key": "total_assets",
        "label": "total retirement savings",
        "question": "About how much total retirement and investment money is there today?",
        "type": "money",
    },
    {
        "key": "annual_spending",
        "label": "annual spending",
        "question": "About how much annual spending should I model in retirement?",
        "type": "money",
    },
    {
        "key": "monthly_social_security",
        "label": "monthly social security",
        "question": "What monthly Social Security amount should I assume for the primary person? If unknown, give a rough number or say 0.",
        "type": "money",
        "default": 0,
    },
]

STATE_ALIASES = {
    "connecticut": "CT",
    "new york": "NY",
    "new jersey": "NJ",
    "massachusetts": "MA",
    "florida": "FL",
    "california": "CA",
    "texas": "TX",
}


@dataclass(frozen=True, slots=True)
class GuidedForecastResult:
    chat_history: list[dict[str, str]]
    state: dict[str, Any]
    key_numbers_markdown: str
    forecast_table: list[list[object]] | None
    account_forecast_table: list[list[object]] | None
    forecast_summary: str
    report_markdown: str
    report_pdf_path: str | None
    workbook_path: str | None
    status_message: str
    ui_values: dict[str, object] | None


def initial_guided_state() -> dict[str, Any]:
    first_question = GUIDED_FIELDS[0]["question"]
    assistant_message = (
        "I will ask you questions to create a basic retirement forecast. "
        "Please respond to each of my questions.\n\n"
        f"{first_question}"
    )
    return {
        "step_index": 0,
        "collected": {},
        "completed": False,
        "chat_history": [{"role": "assistant", "content": assistant_message}],
    }


def ollama_status_text() -> str:
    return provider_status_text()


def reset_guided_conversation() -> GuidedForecastResult:
    state = initial_guided_state()
    return GuidedForecastResult(
        chat_history=state["chat_history"],
        state=state,
        key_numbers_markdown=_guided_placeholder_numbers(),
        forecast_table=None,
        account_forecast_table=None,
        forecast_summary="",
        report_markdown="Run through the guided capture to generate a report here.",
        report_pdf_path=None,
        workbook_path=None,
        status_message="Interactive Guide reset.",
        ui_values=None,
    )


def guided_user_turn(
    user_message: str,
    state: dict[str, Any] | None,
) -> GuidedForecastResult:
    state = _normalize_state(state)
    user_message = (user_message or "").strip()
    if not user_message:
        return GuidedForecastResult(
            chat_history=state["chat_history"],
            state=state,
            key_numbers_markdown=_guided_placeholder_numbers(),
            forecast_table=None,
            account_forecast_table=None,
            forecast_summary="",
            report_markdown="Run through the guided capture to generate a report here.",
            report_pdf_path=None,
            workbook_path=None,
            status_message="Enter a reply to continue the guided flow.",
            ui_values=None,
        )

    state["chat_history"].append({"role": "user", "content": user_message})

    if not state["completed"]:
        field = GUIDED_FIELDS[state["step_index"]]
        extracted = _extract_field_value(field, user_message)
        if extracted is None:
            assistant_message = (
                f"I couldn’t confidently capture the {field['label']} from that reply. "
                f"{field['question']}"
            )
            state["chat_history"].append({"role": "assistant", "content": assistant_message})
            return GuidedForecastResult(
                chat_history=state["chat_history"],
                state=state,
                key_numbers_markdown=_guided_placeholder_numbers(),
                forecast_table=None,
                account_forecast_table=None,
                forecast_summary="",
                report_markdown="Run through the guided capture to generate a report here.",
                report_pdf_path=None,
                workbook_path=None,
                status_message=f"Still waiting on: {field['label']}.",
                ui_values=None,
            )

        state["collected"][field["key"]] = extracted
        state["step_index"] += 1

        if state["step_index"] < len(GUIDED_FIELDS):
            next_field = GUIDED_FIELDS[state["step_index"]]
            assistant_message = _acknowledge_and_ask_next(
                field_label=field["label"],
                field_value=extracted,
                next_question=next_field["question"],
            )
            state["chat_history"].append({"role": "assistant", "content": assistant_message})
            return GuidedForecastResult(
                chat_history=state["chat_history"],
                state=state,
                key_numbers_markdown=_guided_draft_numbers(state["collected"]),
                forecast_table=None,
                account_forecast_table=None,
                forecast_summary="",
                report_markdown="Run through the guided capture to generate a report here.",
                report_pdf_path=None,
                workbook_path=None,
                status_message=f"Captured {field['label']}.",
                ui_values=None,
            )

        state["completed"] = True

    updated_fields = {}
    if state["completed"]:
        updated_fields = _extract_updates(user_message, state["collected"])
        if updated_fields:
            state["collected"].update(updated_fields)

    values = guided_values_to_ui_values(state["collected"])
    plan = ui_values_to_plan(values)
    (
        forecast_table,
        account_forecast_table,
        forecast_summary,
        report_markdown,
        report_pdf_path,
    ) = forecast_with_report_for_ui(plan)
    workbook_path = export_plan_for_ui(plan)
    assistant_message = _guided_result_message(forecast_summary, updated_fields)
    state["chat_history"].append({"role": "assistant", "content": assistant_message})

    return GuidedForecastResult(
        chat_history=state["chat_history"],
        state=state,
        key_numbers_markdown=_forecast_key_numbers(forecast_summary, values),
        forecast_table=forecast_table,
        account_forecast_table=account_forecast_table,
        forecast_summary=forecast_summary,
        report_markdown=report_markdown,
        report_pdf_path=report_pdf_path,
        workbook_path=workbook_path,
        status_message="Interactive Guide ran the forecast successfully.",
        ui_values=values,
    )


def guided_values_to_ui_values(collected: dict[str, Any]) -> dict[str, object]:
    values = plan_to_ui_values(sample_plan())
    base_year = int(collected["base_year"])
    current_age = int(collected["current_age"])
    retirement_age = int(collected["retirement_age"])
    retirement_year = base_year + max(retirement_age - current_age, 0)
    total_assets = float(collected["total_assets"])
    annual_spending = float(collected["annual_spending"])
    monthly_social_security = float(collected["monthly_social_security"])

    values["plan_id"] = _slug(collected["household_name"]) or "guided_case"
    values["household_name"] = str(collected["household_name"])
    values["base_year"] = base_year
    values["state"] = _normalize_state_value(str(collected["state"]))
    values["filing_status"] = "single"
    values["planned_annual_spending"] = _money_string(annual_spending)
    values["target_cash_reserve"] = _money_string(max(annual_spending * 0.72, 10000))
    values["notes"] = "Generated from Interactive Guide straw-man flow."

    primary_person = list(values["people"][0])
    primary_person[2] = str(collected["household_name"])
    primary_person[3] = base_year - current_age
    primary_person[4] = retirement_year
    primary_person[7] = _money_string(monthly_social_security)
    values["people"] = [primary_person]

    snapshot_total = sum(float(str(row[3]).replace(",", "")) for row in values["snapshots"]) or 1.0
    scale = total_assets / snapshot_total

    scaled_accounts = []
    for row in values["accounts"]:
        updated = list(row)
        updated[6] = _money_string(float(str(row[6]).replace(",", "")) * scale)
        scaled_accounts.append(updated)
    values["accounts"] = scaled_accounts

    scaled_holdings = []
    for row in values["holdings"]:
        updated = list(row)
        updated[5] = _money_string(float(str(row[5]).replace(",", "")) * scale)
        scaled_holdings.append(updated)
    values["holdings"] = scaled_holdings

    scaled_snapshots = []
    for row in values["snapshots"]:
        updated = list(row)
        updated[3] = _money_string(float(str(row[3]).replace(",", "")) * scale)
        scaled_snapshots.append(updated)
    values["snapshots"] = scaled_snapshots

    scaled_buckets = []
    for row in values["buckets"]:
        updated = list(row)
        updated[3] = _money_string(float(str(row[3]).replace(",", "")) * scale)
        scaled_buckets.append(updated)
    values["buckets"] = scaled_buckets

    return values


def _normalize_state(state: dict[str, Any] | None) -> dict[str, Any]:
    if not state:
        return initial_guided_state()
    if "chat_history" not in state:
        state["chat_history"] = []
    if "collected" not in state:
        state["collected"] = {}
    state.setdefault("step_index", 0)
    state.setdefault("completed", False)
    return state


def _extract_field_value(field: dict[str, Any], user_message: str) -> Any | None:
    parsed = _llm_extract(
        instructions=(
            f"Extract the user's {field['label']} from their reply. "
            "Return JSON only in the shape {\"value\": ...}. "
            "Use a number for money or integer fields. "
            "Use null when the reply does not contain the requested value."
        ),
        user_message=user_message,
    )
    if parsed is None or parsed.get("value") in (None, ""):
        return _fallback_extract(field["type"], user_message, field.get("default"))
    return _normalize_field_value(field["type"], parsed.get("value"), field.get("default"))


def _extract_updates(user_message: str, current: dict[str, Any]) -> dict[str, Any]:
    parsed = _llm_extract(
        instructions=(
            "Extract any updated retirement-planning fields from the user's message. "
            "Return JSON only with any of these keys when present: "
            "household_name, state, base_year, current_age, retirement_age, "
            "total_assets, annual_spending, monthly_social_security."
        ),
        user_message=user_message,
    ) or {}
    updates: dict[str, Any] = {}
    for field in GUIDED_FIELDS:
        key = field["key"]
        if key in parsed and parsed[key] not in (None, ""):
            updates[key] = _normalize_field_value(field["type"], parsed[key], field.get("default"))
    return updates


def _llm_extract(*, instructions: str, user_message: str) -> dict[str, Any] | None:
    prompt = (
        "You are extracting structured retirement-planning data from a user reply.\n"
        f"{instructions}\n"
        f"User reply: {user_message}\n"
        "Return JSON only."
    )
    try:
        LOGGER.info(
            "Interactive Guide extraction input\ninstructions:\n%s\nuser_input:\n%s",
            instructions,
            user_message,
        )
        response = generate(prompt, json_mode=True, temperature=0.0)
        parsed = json.loads(response)
        LOGGER.info(
            "Interactive Guide extraction parsed output\nparsed_json:\n%s",
            json.dumps(parsed, indent=2, sort_keys=True),
        )
        return parsed
    except Exception:
        return None


def _fallback_extract(field_type: str, user_message: str, default: Any = None) -> Any | None:
    text = user_message.strip()
    if not text:
        return default
    if field_type == "text":
        return text
    if field_type == "state":
        return _normalize_state_value(text)
    if field_type == "int":
        match = re.search(r"\d{1,4}", text.replace(",", ""))
        return int(match.group()) if match else default
    if field_type == "money":
        match = re.search(r"-?\d[\d,]*(?:\.\d+)?", text.replace("$", ""))
        return float(match.group().replace(",", "")) if match else default
    return text


def _normalize_field_value(field_type: str, value: Any, default: Any = None) -> Any:
    if value in (None, ""):
        return default
    if field_type == "text":
        return str(value).strip()
    if field_type == "state":
        return _normalize_state_value(str(value))
    if field_type == "int":
        return int(float(str(value).replace(",", "").strip()))
    if field_type == "money":
        return float(str(value).replace("$", "").replace(",", "").strip())
    return value


def _normalize_state_value(value: str) -> str:
    cleaned = value.strip()
    lowered = cleaned.lower()
    if lowered in STATE_ALIASES:
        return STATE_ALIASES[lowered]
    if len(cleaned) == 2:
        return cleaned.upper()
    return cleaned


def _acknowledge_and_ask_next(*, field_label: str, field_value: Any, next_question: str) -> str:
    pretty_value = field_value if not isinstance(field_value, float) else f"{field_value:,.0f}"
    return f"Captured the {field_label}: `{pretty_value}`.\n\n{next_question}"


def _guided_result_message(summary: str, updated_fields: dict[str, Any]) -> str:
    first_lines = [line for line in summary.splitlines() if line.strip()][:3]
    prefix = "I ran the first forecast." if not updated_fields else "I reran the forecast with your update."
    guidance = (
        "You can now download the PDF report and Excel workbook on the right. "
        "If you want, reply with a change like spending, assets, retirement age, Social Security, state, or base year and I’ll rerun it."
    )
    return prefix + "\n\n" + "\n".join(f"- {line}" for line in first_lines) + "\n\n" + guidance


def _forecast_key_numbers(summary: str, values: dict[str, object]) -> str:
    lines = [line for line in summary.splitlines() if line.strip()]
    bullets = "\n".join(f"- {line}" for line in lines[:6])
    return (
        "### Key Numbers\n"
        f"- **Household:** {values['household_name']}\n"
        f"- **State:** {values['state']}\n"
        f"- **Mode:** interactive guide straw-man\n"
        + bullets
    )


def _guided_placeholder_numbers() -> str:
    return (
        "### Key Numbers\n"
        "- No forecast yet.\n"
        "- Answer the guide questions to generate the first run."
    )


def _guided_draft_numbers(collected: dict[str, Any]) -> str:
    if not collected:
        return _guided_placeholder_numbers()
    lines = ["### Captured So Far"]
    for field in GUIDED_FIELDS:
        key = field["key"]
        if key in collected:
            value = collected[key]
            if isinstance(value, float):
                display = f"{value:,.0f}"
            else:
                display = str(value)
            lines.append(f"- **{field['label'].title()}:** {display}")
    return "\n".join(lines)


def _money_string(value: float) -> str:
    return f"{int(round(value)):,}"


def _slug(value: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower())
    return safe.strip("_")
