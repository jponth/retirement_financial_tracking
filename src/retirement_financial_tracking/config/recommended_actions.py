from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
import json


@dataclass(frozen=True, slots=True)
class RecommendedActionDefinition:
    timing: str
    priority: str
    action: str
    condition: str = "always"


@dataclass(frozen=True, slots=True)
class TriggeredActionDefinition:
    timing: str
    priority: str
    action_template: str
    trigger: str


@dataclass(frozen=True, slots=True)
class RecommendedActionsConfig:
    recurring_actions: tuple[RecommendedActionDefinition, ...]
    triggered_actions: dict[str, TriggeredActionDefinition]


def load_recommended_actions_config() -> RecommendedActionsConfig:
    return _load_recommended_actions_config("default_actions.json")


@lru_cache(maxsize=4)
def _load_recommended_actions_config(filename: str) -> RecommendedActionsConfig:
    package_files = resources.files(
        "retirement_financial_tracking.config.recommended_actions_data"
    )
    raw = json.loads(package_files.joinpath(filename).read_text(encoding="utf-8"))
    recurring_actions = tuple(
        RecommendedActionDefinition(
            timing=str(item["timing"]),
            priority=str(item["priority"]),
            action=str(item["action"]),
            condition=str(item.get("condition") or "always"),
        )
        for item in raw.get("recurring_actions", [])
    )
    triggered_actions = {
        str(item["trigger"]): TriggeredActionDefinition(
            timing=str(item["timing"]),
            priority=str(item["priority"]),
            action_template=str(item["action_template"]),
            trigger=str(item["trigger"]),
        )
        for item in raw.get("triggered_actions", [])
    }
    return RecommendedActionsConfig(
        recurring_actions=recurring_actions,
        triggered_actions=triggered_actions,
    )
