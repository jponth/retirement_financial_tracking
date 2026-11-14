from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import os
from urllib import error, request

LOGGER = logging.getLogger(__name__)


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_value(name: str) -> str | None:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return None
    return value.strip()


def _required_env(name: str) -> str | None:
    value = _env_value(name)
    if value is None:
        LOGGER.error("Required Interactive Guide LLM environment variable is not set: %s", name)
    return value


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
            model=_required_env("IG_LLM_MODEL_NAME"),
            timeout_seconds=int(os.getenv("OLLAMA_TIMEOUT_SECONDS", "45")),
        )


@dataclass(frozen=True, slots=True)
class GroqSettings:
    enabled: bool
    api_key: str | None
    base_url: str
    model: str
    timeout_seconds: int

    @classmethod
    def from_env(cls) -> "GroqSettings":
        api_key = _required_env("IG_LLM_API_KEY")
        model = _required_env("IG_LLM_MODEL_NAME")
        return cls(
            enabled=bool(api_key),
            api_key=api_key,
            base_url=os.getenv("GROQ_BASE_URL", "https://api.groq.com").rstrip("/"),
            model=model or "llama-3.1-8b-instant",
            timeout_seconds=int(os.getenv("GROQ_TIMEOUT_SECONDS", "45")),
        )


@dataclass(frozen=True, slots=True)
class OpenAISettings:
    api_key: str | None
    base_url: str
    model: str
    timeout_seconds: int

    @classmethod
    def from_env(cls) -> "OpenAISettings":
        api_key = _required_env("IG_LLM_API_KEY")
        model = _required_env("IG_LLM_MODEL_NAME")
        return cls(
            api_key=api_key,
            base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com").rstrip("/"),
            model=model or "gpt-5-mini",
            timeout_seconds=int(os.getenv("OPENAI_TIMEOUT_SECONDS", "45")),
        )


def resolve_provider() -> str:
    provider = (_env_value("IG_LLM_PROVIDER_NAME") or "auto").strip().lower()
    if _env_value("IG_LLM_PROVIDER_NAME") is None:
        LOGGER.error(
            "Interactive Guide LLM provider env is not set: IG_LLM_PROVIDER_NAME; defaulting to auto."
        )
    if provider in {"none", "disabled", "off"}:
        return "none"
    if provider in {"ollama", "groq", "openai"}:
        return provider

    groq_settings = GroqSettings.from_env()
    if groq_settings.enabled and groq_settings.api_key:
        return "groq"

    ollama_settings = OllamaSettings.from_env()
    if ollama_settings.enabled:
        return "ollama"

    return "none"


def resolve_model() -> str:
    provider = resolve_provider()
    if provider == "groq":
        settings = GroqSettings.from_env()
        if not settings.api_key:
            raise RuntimeError("IG_LLM_API_KEY is required for Groq.")
        return settings.model
    if provider == "openai":
        settings = OpenAISettings.from_env()
        if not settings.api_key:
            raise RuntimeError("IG_LLM_API_KEY is required for OpenAI.")
        return settings.model
    if provider == "ollama":
        return _resolve_ollama_model(OllamaSettings.from_env())
    raise RuntimeError(
        "No LLM provider is enabled. Configure IG_LLM_API_KEY for hosted use or enable Ollama locally."
    )


def provider_status_text() -> str:
    provider = resolve_provider()
    if provider == "none":
        return "No LLM provider is enabled."
    try:
        model = resolve_model()
    except Exception as exc:
        return f"LLM connection status: `{exc}`"
    return f"LLM provider: `{provider}`. Active model: `{model}`."


def generate(
    prompt: str,
    *,
    model: str | None = None,
    temperature: float = 0.2,
    json_mode: bool = False,
) -> str:
    provider = resolve_provider()
    resolved_model = model or resolve_model()
    LOGGER.info(
        "Interactive Guide LLM request\nprovider=%s\nmodel=%s\njson_mode=%s\ntemperature=%s\nprompt:\n%s",
        provider,
        resolved_model,
        json_mode,
        temperature,
        prompt,
    )
    response_text: str
    if provider == "groq":
        response_text = _generate_groq(
            prompt,
            settings=GroqSettings.from_env(),
            model=resolved_model,
            temperature=temperature,
            json_mode=json_mode,
        )
    elif provider == "openai":
        response_text = _generate_openai(
            prompt,
            settings=OpenAISettings.from_env(),
            model=resolved_model,
            temperature=temperature,
            json_mode=json_mode,
        )
    elif provider == "ollama":
        response_text = _generate_ollama(
            prompt,
            settings=OllamaSettings.from_env(),
            model=resolved_model,
            temperature=temperature,
            json_mode=json_mode,
        )
    else:
        raise RuntimeError(
            "No LLM provider is enabled. Configure IG_LLM_API_KEY for hosted use or enable Ollama locally."
        )
    LOGGER.info(
        "Interactive Guide LLM output\nprovider=%s\nmodel=%s\nresponse:\n%s",
        provider,
        resolved_model,
        response_text,
    )
    return response_text


def _request_json(
    *,
    base_url: str,
    method: str,
    path: str,
    timeout_seconds: int,
    payload: dict | None = None,
    headers: dict[str, str] | None = None,
) -> dict:
    body = None
    merged_headers = {"Content-Type": "application/json"}
    if headers:
        merged_headers.update(headers)
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        f"{base_url}{path}",
        data=body,
        headers=merged_headers,
        method=method,
    )
    try:
        with request.urlopen(req, timeout=timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace").strip()
        raise RuntimeError(
            f"LLM request failed with HTTP {exc.code}: {detail or exc.reason}"
        ) from exc
    except error.URLError as exc:
        raise RuntimeError(f"Unable to reach LLM endpoint at {base_url}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("LLM provider returned invalid JSON.") from exc


def _list_ollama_models(settings: OllamaSettings) -> list[str]:
    if not settings.enabled:
        return []
    payload = _request_json(
        base_url=settings.base_url,
        method="GET",
        path="/api/tags",
        timeout_seconds=settings.timeout_seconds,
    )
    return [
        item.get("name", "").strip()
        for item in payload.get("models", [])
        if item.get("name", "").strip()
    ]


def _resolve_ollama_model(settings: OllamaSettings) -> str:
    if settings.model:
        return settings.model
    raise RuntimeError("IG_LLM_MODEL_NAME is required for Ollama.")


def _generate_ollama(
    prompt: str,
    *,
    settings: OllamaSettings,
    model: str | None,
    temperature: float,
    json_mode: bool,
) -> str:
    if not settings.enabled:
        raise RuntimeError("Ollama integration is disabled.")
    resolved_model = model or _resolve_ollama_model(settings)
    payload: dict[str, object] = {
        "model": resolved_model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": temperature},
    }
    if json_mode:
        payload["format"] = "json"
    response = _request_json(
        base_url=settings.base_url,
        method="POST",
        path="/api/generate",
        timeout_seconds=settings.timeout_seconds,
        payload=payload,
    )
    text = str(response.get("response", "")).strip()
    if not text:
        raise RuntimeError("Ollama returned an empty response.")
    return text


def _generate_groq(
    prompt: str,
    *,
    settings: GroqSettings,
    model: str | None,
    temperature: float,
    json_mode: bool,
) -> str:
    if not settings.enabled or not settings.api_key:
        raise RuntimeError("Groq integration is disabled or missing IG_LLM_API_KEY.")
    payload: dict[str, object] = {
        "model": model or settings.model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    response = _request_json(
        base_url=settings.base_url,
        method="POST",
        path="/openai/v1/chat/completions",
        timeout_seconds=settings.timeout_seconds,
        payload=payload,
        headers={"Authorization": f"Bearer {settings.api_key}"},
    )
    choices = response.get("choices") or []
    if not choices:
        raise RuntimeError("Groq returned no choices.")
    text = str(((choices[0] or {}).get("message") or {}).get("content") or "").strip()
    if not text:
        raise RuntimeError("Groq returned an empty response.")
    return text


def _generate_openai(
    prompt: str,
    *,
    settings: OpenAISettings,
    model: str | None,
    temperature: float,
    json_mode: bool,
) -> str:
    if not settings.api_key:
        raise RuntimeError("OpenAI integration is disabled or missing IG_LLM_API_KEY.")
    payload: dict[str, object] = {
        "model": model or settings.model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    response = _request_json(
        base_url=settings.base_url,
        method="POST",
        path="/v1/chat/completions",
        timeout_seconds=settings.timeout_seconds,
        payload=payload,
        headers={"Authorization": f"Bearer {settings.api_key}"},
    )
    choices = response.get("choices") or []
    if not choices:
        raise RuntimeError("OpenAI returned no choices.")
    text = str(((choices[0] or {}).get("message") or {}).get("content") or "").strip()
    if not text:
        raise RuntimeError("OpenAI returned an empty response.")
    return text
