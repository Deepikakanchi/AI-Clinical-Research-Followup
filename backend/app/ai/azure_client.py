"""Calls the existing Microsoft Foundry deployment and defines AI errors (US-17, US-21, US-31).

- Configured entirely from environment variables (AIConfig).
- The underlying SDK client can be injected, so tests use a fake and never hit Azure.
- Retries only transient failures (timeout, network, 5xx), never 429 or content-filter blocks.
- Logs deployment, model, latency and outcome only: never note text, codes or the key.
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

import openai
from app.core.logging_config import log_event

# ------------------------------------------------------------------ errors
# Every failure carries an error_code (stored in ai_summaries.error_code) and the HTTP
# status the API returns. The user-facing message is always the same, so no provider
# detail or note text ever reaches the browser.

USER_MESSAGE = "Draft unavailable, try again later"

# error_code -> HTTP status
AI_DISABLED = "AI_DISABLED"                    # 503: AI_ENABLED=false
QUOTA_EXCEEDED = "QUOTA_EXCEEDED"              # 503: 429 from Foundry
CREDENTIAL_ERROR = "CREDENTIAL_ERROR"          # 503: invalid key / no permission
DEPLOYMENT_NOT_FOUND = "DEPLOYMENT_NOT_FOUND"  # 503: wrong deployment name
PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"  # 503: network failure
TIMEOUT = "TIMEOUT"                            # 504: no reply within AI_TIMEOUT_SECONDS
CONTENT_FILTER = "CONTENT_FILTER"              # 502: Foundry guardrail blocked input or output
INVALID_OUTPUT = "INVALID_OUTPUT"              # 502: reply not valid SummaryDraft, or incomplete
UNGROUNDED_OUTPUT = "UNGROUNDED_OUTPUT"        # 502: invented action, number or blocked wording
PROVIDER_ERROR = "PROVIDER_ERROR"              # 502: any other provider error

STATUS_BY_CODE = {
    AI_DISABLED: 503,
    QUOTA_EXCEEDED: 503,
    CREDENTIAL_ERROR: 503,
    DEPLOYMENT_NOT_FOUND: 503,
    PROVIDER_UNAVAILABLE: 503,
    TIMEOUT: 504,
    CONTENT_FILTER: 502,
    INVALID_OUTPUT: 502,
    UNGROUNDED_OUTPUT: 502,
    PROVIDER_ERROR: 502,
}


class AIError(Exception):
    """A controlled AI failure. `reason` is for logs only and never holds note text."""

    def __init__(
        self,
        error_code: str,
        reason: str = "",
        *,
        latency_ms: Optional[int] = None,
        model_id: Optional[str] = None,
    ) -> None:
        super().__init__(f"{error_code}: {reason}" if reason else error_code)
        self.error_code = error_code
        self.status_code = STATUS_BY_CODE.get(error_code, 502)
        self.reason = reason
        self.latency_ms = latency_ms
        self.model_id = model_id


# ------------------------------------------------------------------ client

logger = logging.getLogger("app.ai")

ENTRA_SCOPE = "https://ai.azure.com/.default"


def _as_bool(value: Any, default: bool) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _as_float_or_none(value: Any) -> Optional[float]:
    if value is None or str(value).strip() == "":
        return None
    return float(value)


@dataclass(frozen=True)
class AIConfig:
    endpoint: str
    deployment: str
    api_key: str = field(default="", repr=False)  # empty -> Microsoft Entra ID sign-in
    api_version: str = ""                         # empty -> GA v1 API (/openai/v1/)
    timeout_seconds: float = 20.0
    max_retries: int = 1
    enabled: bool = True
    reasoning_effort: Optional[str] = "low"       # "none", "low", ... or None to omit
    temperature: Optional[float] = None           # GPT-5.4 models reject temperature; leave None
    max_completion_tokens: int = 2000

    @classmethod
    def from_mapping(cls, env: Mapping[str, Any]) -> "AIConfig":
        def get(name: str, default: Any = None) -> Any:
            value = env.get(name)
            if value is None:
                value = env.get(name.lower())
            return default if value is None else value

        effort = str(get("AI_REASONING_EFFORT", "low")).strip()
        return cls(
            endpoint=str(get("AZURE_OPENAI_ENDPOINT", "")).strip(),
            deployment=str(get("AZURE_OPENAI_DEPLOYMENT", "")).strip(),
            api_key=str(get("AZURE_OPENAI_API_KEY", "")).strip(),
            api_version=str(get("AZURE_OPENAI_API_VERSION", "")).strip(),
            timeout_seconds=float(get("AI_TIMEOUT_SECONDS", 20)),
            max_retries=int(get("AI_MAX_RETRIES", 1)),
            enabled=_as_bool(get("AI_ENABLED"), True),
            reasoning_effort=effort or None,
            temperature=_as_float_or_none(get("AI_TEMPERATURE")),
            max_completion_tokens=int(get("AI_MAX_COMPLETION_TOKENS", 2000)),
        )

    @classmethod
    def from_env(cls) -> "AIConfig":
        return cls.from_mapping(os.environ)

    @classmethod
    def from_settings(cls, settings: Any) -> "AIConfig":
        """Adapter for Person 1's core/config.py settings object (upper- or lower-case fields)."""
        names = [
            "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_DEPLOYMENT", "AZURE_OPENAI_API_KEY",
            "AZURE_OPENAI_API_VERSION", "AI_TIMEOUT_SECONDS", "AI_MAX_RETRIES", "AI_ENABLED",
            "AI_REASONING_EFFORT", "AI_TEMPERATURE", "AI_MAX_COMPLETION_TOKENS",
        ]
        values: dict[str, Any] = {}
        for name in names:
            value = getattr(settings, name, None)
            if value is None:
                value = getattr(settings, name.lower(), None)
            if hasattr(value, "get_secret_value"):
                value = value.get_secret_value()
            if value is not None:
                values[name] = value
        return cls.from_mapping(values)


@dataclass(frozen=True)
class AIResult:
    content: str
    model_id: Optional[str]
    deployment: str
    latency_ms: int


def build_openai_client(config: AIConfig) -> Any:
    """Create the real SDK client. Retries are handled by SummaryClient, so the SDK's are off."""
    if not config.endpoint or not config.deployment:
        raise AIError(CREDENTIAL_ERROR, "AZURE_OPENAI_ENDPOINT or AZURE_OPENAI_DEPLOYMENT is not set")

    credential: Any = config.api_key
    if not credential:
        try:
            from azure.identity import DefaultAzureCredential, get_bearer_token_provider
        except ImportError:
            raise AIError(CREDENTIAL_ERROR, "no API key set and azure-identity is not installed") from None
        credential = get_bearer_token_provider(DefaultAzureCredential(), ENTRA_SCOPE)

    if config.api_version:
        kwargs: dict[str, Any] = {
            "azure_endpoint": config.endpoint,
            "api_version": config.api_version,
            "timeout": config.timeout_seconds,
            "max_retries": 0,
        }
        if config.api_key:
            kwargs["api_key"] = config.api_key
        else:
            kwargs["azure_ad_token_provider"] = credential
        return openai.AzureOpenAI(**kwargs)

    base_url = config.endpoint.rstrip("/")
    if not base_url.endswith("/v1"):  # Azure resource URL gets /openai/v1; OpenRouter's URL already ends in /v1
        base_url += "/openai/v1"
    return openai.OpenAI(base_url=base_url + "/", api_key=credential, timeout=config.timeout_seconds, max_retries=0)


def _is_content_filter(exc: openai.APIStatusError) -> bool:
    if getattr(exc, "code", None) == "content_filter":
        return True
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        if body.get("code") == "content_filter":
            return True
        inner = body.get("error")
        if isinstance(inner, dict) and inner.get("code") == "content_filter":
            return True
    return "content_filter" in str(exc).lower()


TRANSIENT_ERRORS = (openai.APITimeoutError, openai.APIConnectionError, openai.InternalServerError)


class SummaryClient:
    """Thin wrapper around chat completions with project-specific failure handling."""

    def __init__(self, config: AIConfig, client: Any = None) -> None:
        self.config = config
        self._client = client

    def _sdk(self) -> Any:
        if self._client is None:
            self._client = build_openai_client(self.config)
        return self._client

    def _request_kwargs(self, messages: list[dict], json_schema: dict) -> dict:
        kwargs: dict[str, Any] = {
            "model": self.config.deployment,
            "messages": messages,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "SummaryDraft", "strict": True, "schema": json_schema},
            },
            "max_completion_tokens": self.config.max_completion_tokens,
        }
        if self.config.reasoning_effort:
            kwargs["reasoning_effort"] = self.config.reasoning_effort
        if self.config.temperature is not None:
            kwargs["temperature"] = self.config.temperature
        return kwargs

    def _fail(self, code: str, reason: str, started: float, model_id: Optional[str] = None) -> AIError:
        latency_ms = int((time.perf_counter() - started) * 1000)
        log_event(logger, "ai_call", logging.WARNING, deployment=self.config.deployment, model_id=model_id,
                  latency_ms=latency_ms, outcome="FAILED", error_code=code)
        return AIError(code, reason, latency_ms=latency_ms, model_id=model_id)

    def _map_exception(self, exc: Exception, started: float) -> AIError:
        if isinstance(exc, openai.APITimeoutError):
            return self._fail(TIMEOUT, "request timed out", started)
        if isinstance(exc, openai.APIConnectionError):
            return self._fail(PROVIDER_UNAVAILABLE, "could not reach the endpoint", started)
        if isinstance(exc, openai.RateLimitError):
            return self._fail(QUOTA_EXCEEDED, "429 from deployment", started)
        if isinstance(exc, (openai.AuthenticationError, openai.PermissionDeniedError)):
            return self._fail(CREDENTIAL_ERROR, f"{exc.status_code} credential rejected", started)
        if isinstance(exc, openai.NotFoundError):
            return self._fail(DEPLOYMENT_NOT_FOUND, "404 deployment not found", started)
        if isinstance(exc, openai.BadRequestError) and _is_content_filter(exc):
            return self._fail(CONTENT_FILTER, "request blocked by Foundry guardrails", started)
        if isinstance(exc, openai.APIStatusError):
            return self._fail(PROVIDER_ERROR, f"{exc.status_code} from provider", started)
        return self._fail(PROVIDER_ERROR, type(exc).__name__, started)

    def generate(self, messages: list[dict], json_schema: dict) -> AIResult:
        if not self.config.enabled:
            raise AIError(AI_DISABLED, "AI_ENABLED is false", latency_ms=0)

        started = time.perf_counter()
        sdk = self._sdk()
        kwargs = self._request_kwargs(messages, json_schema)
        attempts = 1 + max(0, self.config.max_retries)

        response = None
        for attempt in range(attempts):
            try:
                response = sdk.chat.completions.create(**kwargs)
                break
            except TRANSIENT_ERRORS as exc:
                if attempt < attempts - 1:
                    log_event(logger, "ai_retry", logging.INFO, deployment=self.config.deployment,
                              attempt=attempt + 1, error_type=type(exc).__name__)
                    continue
                raise self._map_exception(exc, started) from None
            except openai.APIError as exc:
                raise self._map_exception(exc, started) from None

        model_id = getattr(response, "model", None)
        choices = getattr(response, "choices", None) or []
        if not choices:
            raise self._fail(INVALID_OUTPUT, "no choices in reply", started, model_id)

        choice = choices[0]
        finish_reason = getattr(choice, "finish_reason", None)
        message = getattr(choice, "message", None)
        if finish_reason == "content_filter":
            raise self._fail(CONTENT_FILTER, "reply withheld by Foundry guardrails", started, model_id)
        if finish_reason == "length":
            raise self._fail(INVALID_OUTPUT, "reply incomplete: hit max_completion_tokens", started, model_id)
        if message is not None and getattr(message, "refusal", None):
            raise self._fail(INVALID_OUTPUT, "model refused", started, model_id)
        content = getattr(message, "content", None) if message is not None else None
        if not content or not str(content).strip():
            raise self._fail(INVALID_OUTPUT, "empty reply", started, model_id)

        latency_ms = int((time.perf_counter() - started) * 1000)
        log_event(logger, "ai_call", logging.INFO, deployment=self.config.deployment, model_id=model_id,
                  latency_ms=latency_ms, outcome="SUCCEEDED")
        return AIResult(content=str(content), model_id=model_id, deployment=self.config.deployment, latency_ms=latency_ms)