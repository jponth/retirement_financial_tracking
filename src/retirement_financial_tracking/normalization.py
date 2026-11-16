from __future__ import annotations

from retirement_financial_tracking.domain.models import AccountType

def valid_account_type_values() -> list[str]:
    return [member.value for member in AccountType]


def parse_account_type_value(value: object) -> AccountType:
    normalized = str(value or AccountType.OTHER.value).strip().lower()
    try:
        return AccountType(normalized or AccountType.OTHER.value)
    except ValueError as exc:
        raise ValueError(
            "Invalid account_type "
            f"`{normalized or value}`. Valid values: {', '.join(valid_account_type_values())}"
        ) from exc
