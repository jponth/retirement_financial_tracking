from __future__ import annotations

from pathlib import Path
import tomllib

from pydantic import BaseModel, Field


class AppMetadata(BaseModel):
    product_display_name: str = Field(min_length=1)
    product_short_name: str = Field(min_length=1)
    default_workbook_name: str = Field(min_length=1)


def _default_config_path() -> Path:
    return Path(__file__).resolve().parents[3] / "config" / "app_config.toml"


def load_app_metadata(path: str | Path | None = None) -> AppMetadata:
    config_path = Path(path) if path is not None else _default_config_path()
    with config_path.open("rb") as handle:
        data = tomllib.load(handle)
    return AppMetadata.model_validate(data)

