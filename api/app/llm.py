"""Centralized, type-safe construction of chat LLM clients.

All ``ChatOpenAI`` instantiation flows through :func:`make_chat_llm` so the
OpenAI-specific quirks (``SecretStr`` API keys, the ``max_completion_tokens``
field alias) live in exactly one place instead of being repeated at every
call site.

Observability lives here for the same reason. Instrumentation used to be a
per-call-site decision and most sites simply forgot, so an outage on an
uninstrumented path (Spark exhausting its OpenAI credit) surfaced as an
unexplained gateway error with nothing in the log naming the cause. Every
client built here now carries
:class:`~app.logging_conf.LLMTelemetryCallbackHandler`, and
:func:`describe_llm_error` gives every caller one vocabulary for provider
failures instead of each inventing its own.
"""

from __future__ import annotations

from dataclasses import dataclass

from langchain_core.callbacks import BaseCallbackHandler
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from app.logging_conf import LLMTelemetryCallbackHandler

__all__ = ["LLMFailure", "describe_llm_error", "make_chat_llm"]

# Provider codes meaning "the account cannot pay for this call" rather than
# "you are going too fast". Both arrive as HTTP 429, but only the latter is
# worth retrying, and conflating them is what let a billing outage read as a
# transient blip.
_QUOTA_CODES = frozenset({"insufficient_quota", "credit_balance_exhausted"})


@dataclass(frozen=True)
class LLMFailure:
    """A provider failure reduced to the few facts worth acting on.

    ``kind`` is a small stable vocabulary so log lines and alerts can match on
    it without parsing provider prose, which differs between models and changes
    without notice.
    """

    kind: str
    status: int | None
    code: str | None
    message: str

    @property
    def retryable(self) -> bool:
        return self.kind in ("rate_limit", "timeout", "connection", "provider_error")

    def summary(self) -> str:
        """One-line, greppable description carrying no provider prose."""
        parts = [f"kind={self.kind}"]
        if self.status is not None:
            parts.append(f"status={self.status}")
        if self.code:
            parts.append(f"code={self.code}")
        return " ".join(parts)


def _error_body_field(exc: BaseException, field: str) -> str | None:
    """Pull ``field`` out of an OpenAI-shaped error body, if there is one."""
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict) and isinstance(error.get(field), str):
            return str(error[field])
        if isinstance(body.get(field), str):
            return str(body[field])
    direct = getattr(exc, field, None)
    return direct if isinstance(direct, str) else None


def describe_llm_error(exc: BaseException) -> LLMFailure:
    """Classify a provider exception without depending on provider classes.

    Read by attribute rather than by ``isinstance`` so this keeps working across
    ``openai``/``langchain`` releases that reshuffle their exception hierarchies.
    A classifier that silently degraded to "unknown" on every upgrade would
    defeat the point of having one.
    """
    status = getattr(exc, "status_code", None)
    if not isinstance(status, int):
        status = None
    code = _error_body_field(exc, "code") or _error_body_field(exc, "type")
    message = str(exc).strip() or type(exc).__name__
    name = type(exc).__name__
    lowered = message.lower()

    if isinstance(exc, TimeoutError) or "Timeout" in name:
        kind = "timeout"
    elif isinstance(exc, ConnectionError) or "Connection" in name:
        kind = "connection"
    elif status == 429 and (
        code in _QUOTA_CODES or "quota" in lowered or "credit" in lowered
    ):
        kind = "quota"
    elif status == 429:
        kind = "rate_limit"
    elif status in (401, 403):
        kind = "auth"
    elif status is not None and 400 <= status < 500:
        kind = "invalid_request"
    elif status is not None and status >= 500:
        kind = "provider_error"
    else:
        kind = "unknown"

    return LLMFailure(kind=kind, status=status, code=code, message=message)


def make_chat_llm(
    *,
    model: str,
    api_key: str,
    temperature: float | None = None,
    max_tokens: int | None = None,
    callbacks: list[BaseCallbackHandler] | None = None,
) -> ChatOpenAI:
    """Build a :class:`ChatOpenAI` client with type-correct arguments.

    ``api_key`` is accepted as a plain ``str`` and wrapped in ``SecretStr`` so
    callers never handle the secret type directly. ``max_tokens`` is forwarded
    via the ``max_completion_tokens`` field alias expected by current
    ``langchain-openai`` releases. Telemetry is prepended to ``callbacks`` and
    is not opt-out: the call sites that most needed it were the ones that never
    asked for it.
    """
    handlers: list[BaseCallbackHandler] = [LLMTelemetryCallbackHandler()]
    handlers.extend(callbacks or [])
    return ChatOpenAI(
        model=model,
        api_key=SecretStr(api_key),
        temperature=temperature,
        max_completion_tokens=max_tokens,
        callbacks=handlers,
    )
