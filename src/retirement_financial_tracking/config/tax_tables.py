from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
from importlib import resources
import json

from retirement_financial_tracking.domain.models import FilingStatus


@dataclass(frozen=True, slots=True)
class TaxBracket:
    upper_bound: Decimal | None
    rate: Decimal


@dataclass(frozen=True, slots=True)
class TaxTable:
    base_year: int
    standard_deduction_by_status: dict[FilingStatus, Decimal]
    brackets_by_status: dict[FilingStatus, tuple[TaxBracket, ...]]
    exemption_by_status: dict[FilingStatus, tuple[tuple[Decimal | None, Decimal], ...]] | None = None


def load_federal_tax_table() -> TaxTable:
    return _load_tax_table("federal_us.json")


def load_connecticut_tax_table() -> TaxTable:
    return _load_tax_table("state_ct.json")


@lru_cache(maxsize=8)
def _load_tax_table(filename: str) -> TaxTable:
    package_files = resources.files("retirement_financial_tracking.config.tax_tables_data")
    raw = json.loads(package_files.joinpath(filename).read_text(encoding="utf-8"))
    return TaxTable(
        base_year=int(raw["base_year"]),
        standard_deduction_by_status=_parse_amount_map(raw.get("standard_deduction", {})),
        brackets_by_status=_parse_brackets(raw["ordinary_income_brackets"]),
        exemption_by_status=_parse_exemption_map(raw.get("income_based_exemption")),
    )


def _parse_amount_map(raw: dict[str, float | int | str]) -> dict[FilingStatus, Decimal]:
    return {FilingStatus(key): Decimal(str(value)) for key, value in raw.items()}


def _parse_brackets(
    raw: dict[str, list[dict[str, float | int | str | None]]]
) -> dict[FilingStatus, tuple[TaxBracket, ...]]:
    parsed: dict[FilingStatus, tuple[TaxBracket, ...]] = {}
    for status, brackets in raw.items():
        parsed[FilingStatus(status)] = tuple(
            TaxBracket(
                upper_bound=None
                if bracket.get("up_to") is None
                else Decimal(str(bracket["up_to"])),
                rate=Decimal(str(bracket["rate"])),
            )
            for bracket in brackets
        )
    return parsed


def _parse_exemption_map(
    raw: dict[str, list[dict[str, float | int | str | None]]] | None,
) -> dict[FilingStatus, tuple[tuple[Decimal | None, Decimal], ...]] | None:
    if not raw:
        return None
    parsed: dict[FilingStatus, tuple[tuple[Decimal | None, Decimal], ...]] = {}
    for status, tiers in raw.items():
        parsed[FilingStatus(status)] = tuple(
            (
                None if tier.get("up_to") is None else Decimal(str(tier["up_to"])),
                Decimal(str(tier["amount"])),
            )
            for tier in tiers
        )
    return parsed
