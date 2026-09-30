"""Tests for LLM client construction, instrumentation, and error classification.

The failure that motivated this module was a Spark outage in which OpenAI
credits ran out: the provider answered `429 insufficient_quota`, the route
reported a blanket gateway error, and nothing in the logs named the cause.
These tests pin the two properties that would have made it a one-line
diagnosis — every client is instrumented, and every provider failure is
classified into a stable vocabulary.
"""

from __future__ import annotations

from typing import Any

from app.llm import LLMFailure, describe_llm_error, make_chat_llm
from app.logging_conf import LLMTelemetryCallbackHandler
from langchain_core.callbacks import BaseCallbackHandler


class _ProviderError(Exception):
    """Stands in for an ``openai`` error without importing its class hierarchy.

    Matching the real classes by name would make these tests re-pass trivially
    on an SDK upgrade that renamed them, which is the exact regression
    :func:`describe_llm_error` is written to survive.
    """

    def __init__(self, message: str, status_code: int, body: Any) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body = body


def _openai_body(code: str, message: str, type_: str = "error") -> dict[str, Any]:
    return {"error": {"message": message, "type": type_, "code": code}}


class TestDescribeLLMError:
    def test_classifies_exhausted_credit_as_quota(self) -> None:
        """The real outage: 429 that no amount of retrying will fix."""
        exc = _ProviderError(
            "Error code: 429 - You have no credits remaining.",
            429,
            _openai_body("credit_balance_exhausted", "You have no credits remaining."),
        )
        failure = describe_llm_error(exc)
        assert failure.kind == "quota"
        assert failure.status == 429
        assert failure.code == "credit_balance_exhausted"
        assert failure.retryable is False

    def test_distinguishes_rate_limit_from_quota(self) -> None:
        """Both are 429, but only one is worth retrying."""
        exc = _ProviderError(
            "Rate limit reached", 429, _openai_body("rate_limit_exceeded", "slow down")
        )
        failure = describe_llm_error(exc)
        assert failure.kind == "rate_limit"
        assert failure.retryable is True

    def test_classifies_auth(self) -> None:
        exc = _ProviderError(
            "Incorrect API key", 401, _openai_body("invalid_api_key", "bad key")
        )
        failure = describe_llm_error(exc)
        assert failure.kind == "auth"
        assert failure.retryable is False

    def test_classifies_timeout_and_connection(self) -> None:
        assert describe_llm_error(TimeoutError("timed out")).kind == "timeout"
        assert describe_llm_error(ConnectionError("no route")).kind == "connection"

    def test_classifies_provider_outage(self) -> None:
        exc = _ProviderError("Bad gateway", 503, _openai_body("", "upstream down"))
        failure = describe_llm_error(exc)
        assert failure.kind == "provider_error"
        assert failure.retryable is True

    def test_unrecognised_error_is_never_fatal_to_classify(self) -> None:
        """An unknown shape must still yield a usable record, not raise."""
        failure = describe_llm_error(RuntimeError("something odd"))
        assert failure == LLMFailure(
            kind="unknown", status=None, code=None, message="something odd"
        )

    def test_summary_is_greppable_and_carries_no_provider_prose(self) -> None:
        exc = _ProviderError(
            "You have no credits remaining. Add credits at https://example.com/billing",
            429,
            _openai_body("insufficient_quota", "no credits"),
        )
        summary = describe_llm_error(exc).summary()
        assert summary == "kind=quota status=429 code=insufficient_quota"
        assert "https://" not in summary


class TestMakeChatLLM:
    def test_always_attaches_telemetry(self) -> None:
        """Instrumentation must not be something a call site can forget."""
        llm = make_chat_llm(model="gpt-4o-mini", api_key="sk-test")
        assert any(
            isinstance(cb, LLMTelemetryCallbackHandler) for cb in (llm.callbacks or [])
        )

    def test_caller_callbacks_are_kept_alongside_telemetry(self) -> None:
        extra = BaseCallbackHandler()
        llm = make_chat_llm(model="gpt-4o-mini", api_key="sk-test", callbacks=[extra])
        callbacks = list(llm.callbacks or [])
        assert extra in callbacks
        assert any(isinstance(cb, LLMTelemetryCallbackHandler) for cb in callbacks)
