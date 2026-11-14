from __future__ import annotations

from dataclasses import dataclass
import json
import os
from urllib import error, request


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class OllamaSettings:
    enabled: bool
    base_url: str
    model: str | None
    timeout_seconds: int

    @classmethod
    def from_env(cls) -> "OllamaSettings":
        return cls(
            enabled=_env_flag("OLLAMA_ENABLED", default=True),
            base_url=os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/"),
            model=(os.getenv("OLLAMA_MODEL") or "").strip() or None,
            timeout_seconds=int(os.getenv("OLLAMA_TIMEOUT_SECONDS", "45")),
        )


def _request_json(settings: OllamaSettings, method: str, path: str, payload: dict | None = None) -> dict:
    body = None
    headers = {"Content-Type": "application/json"}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        f"{settings.base_url}{path}",
        data=body,
        headers=headers,
        method=method,
    )
    try:
        with request.urlopen(req, timeout=settings.timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))
    except error.URLError as exc:
        raise RuntimeError(f"Unable to reach Ollama at {settings.base_url}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("Ollama returned invalid JSON.") from exc


def list_models(settings: OllamaSettings | None = None) -> list[str]:
    settings = settings or OllamaSettings.from_env()
    if not settings.enabled:
        return []
    payload = _request_json(settings, "GET", "/api/tags")
    return [
        item.get("name", "").strip()
        for item in payload.get("models", [])
        if item.get("name", "").strip()
    ]


def resolve_model(settings: OllamaSettings | None = None) -> str:
    settings = settings or OllamaSettings.from_env()
    if settings.model:
        return settings.model
    models = list_models(settings)
    if not models:
        raise RuntimeError(
            "No Ollama models are available. Set OLLAMA_MODEL or pull a local model first."
        )
    return models[0]


def generate(
    prompt: str,
    *,
    settings: OllamaSettings | None = None,
    model: str | None = None,
    temperature: float = 0.2,
    json_mode: bool = False,
) -> str:
    settings = settings or OllamaSettings.from_env()
    if not settings.enabled:
        raise RuntimeError("Ollama integration is disabled.")
    resolved_model = model or resolve_model(settings)
    payload: dict[str, object] = {
        "model": resolved_model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
        },
    }
    if json_mode:
        payload["format"] = "json"
    response = _request_json(settings, "POST", "/api/generate", payload)
    text = str(response.get("response", "")).strip()
    if not text:
        raise RuntimeError("Ollama returned an empty response.")
    return text
