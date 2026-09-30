"""Centralized logging configuration and observability tools.

Logging is described in exactly one place — :func:`build_logging_config`, a
declarative ``logging.config.dictConfig`` dictionary — and applied via
:func:`configure_logging`. There is no imperative handler juggling and no
import-time side effect: configuration happens **once, at each process entry
point** (the API lifespan in :mod:`app.main`, the worker in
:mod:`app.worker.notification_worker`) and the very same description is handed to
uvicorn (see :mod:`app.serve`). That single source of truth is what keeps one
change from quietly interacting with another: there is only ever one logging
system, not the application's and uvicorn's competing for the root logger.
"""

from __future__ import annotations

import json
import logging
import logging.config
import os
import time
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import BaseMessage
from langchain_core.outputs import LLMResult

from app import config

# Correlation id for the in-flight request, stamped onto every log record by
# :class:`RequestIdFilter`. A ContextVar (not a thread-local) because request
# handling is async: every task spawned inside a request inherits the value, so
# a line logged deep in a service still carries the id of the request that
# caused it. "-" is what background work and startup lines show.
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

# Single human-readable line format shared by every handler and every process.
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s [%(request_id)s]: %(message)s"

# Third-party loggers that are too chatty at INFO; pinned to WARNING.
_QUIET_LIBRARIES = ("httpx", "httpcore")


class RequestIdFilter(logging.Filter):
    """Attach the current request id to every record.

    Installed on the handlers rather than on individual loggers so that records
    from third-party libraries — which never heard of this application — still
    format against :data:`LOG_FORMAT` instead of raising ``KeyError``.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


def _resolve_log_file() -> str | None:
    """Return the path of the app log file, or ``None`` if it cannot be used.

    File logging is best-effort. If the data directory cannot be created (for
    example on a read-only filesystem) we fall back to console-only logging
    instead of failing process startup. The console handler — captured by
    ``docker logs`` — is always present regardless.
    """
    data_dir = config.get_data_dir()
    try:
        os.makedirs(data_dir, exist_ok=True)
    except OSError:
        return None
    return os.path.join(data_dir, "app.log")


def build_logging_config(*, log_level: str | None = None) -> dict[str, Any]:
    """Return the declarative ``dictConfig`` description of Flow's logging.

    This is the single source of truth. It is consumed by
    :func:`configure_logging` for the current process and is also passed to
    ``uvicorn.run(log_config=...)`` so uvicorn does not install a competing
    configuration. ``disable_existing_loggers`` is ``False`` so loggers created
    at import time keep working; uvicorn's loggers are given no handlers of their
    own and propagate to the root so access/error lines share the application's
    format and sinks.
    """
    level = (log_level or config.get_log_level()).upper()

    handlers: dict[str, dict[str, Any]] = {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "flow",
            "filters": ["request_id"],
            "stream": "ext://sys.stdout",
        },
    }
    root_handlers = ["console"]

    log_file = _resolve_log_file()
    if log_file is not None:
        handlers["file"] = {
            "class": "logging.handlers.WatchedFileHandler",
            "formatter": "flow",
            "filters": ["request_id"],
            "filename": log_file,
            "encoding": "utf-8",
        }
        root_handlers.append("file")

    uvicorn_logger = {"level": level, "handlers": [], "propagate": True}

    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {"flow": {"format": LOG_FORMAT}},
        "filters": {"request_id": {"()": f"{__name__}.RequestIdFilter"}},
        "handlers": handlers,
        "root": {"level": level, "handlers": root_handlers},
        "loggers": {
            **{name: {"level": "WARNING"} for name in _QUIET_LIBRARIES},
            "uvicorn": uvicorn_logger,
            "uvicorn.error": uvicorn_logger,
            "uvicorn.access": uvicorn_logger,
        },
    }


def configure_logging(*, log_level: str | None = None) -> dict[str, Any]:
    """Apply Flow's logging configuration to the current process.

    Returns the applied configuration so callers (notably :mod:`app.serve`) can
    hand the exact same description to uvicorn. ``logging.config.dictConfig``
    replaces the configuration deterministically on every call, so this is safe
    to call more than once. Call it only at a process entry point — never at
    import time — because applying the root configuration replaces the root
    logger's handlers (which is precisely why tests, which own their own
    handlers via ``caplog``, must not trigger it).
    """
    cfg = build_logging_config(log_level=log_level)
    logging.config.dictConfig(cfg)
    return cfg


class LLMTelemetryCallbackHandler(BaseCallbackHandler):
    """Always-on, content-free record of every model call.

    Attached automatically by :func:`app.llm.make_chat_llm`, so visibility is a
    property of making a model call rather than something each call site has to
    remember — the omission that made a quota outage look like an unexplained
    gateway error. Deliberately metadata only: model, duration, token usage, and
    on failure the provider's status and code. Prompts and completions are the
    business of :class:`LLMLoggingCallbackHandler`, which stays opt-in because
    it writes user content to disk.
    """

    def __init__(self) -> None:
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self._started: dict[UUID, float] = {}

    def _elapsed_ms(self, run_id: UUID | None) -> float | None:
        if run_id is None:
            return None
        started = self._started.pop(run_id, None)
        return None if started is None else (time.perf_counter() - started) * 1000

    def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[BaseMessage]],
        **kwargs: Any,
    ) -> None:
        run_id = kwargs.get("run_id")
        if run_id is not None:
            self._started[run_id] = time.perf_counter()

    def on_llm_start(
        self, serialized: dict[str, Any], prompts: list[str], **kwargs: Any
    ) -> None:
        self.on_chat_model_start(serialized, [], **kwargs)

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        elapsed = self._elapsed_ms(kwargs.get("run_id"))
        output = response.llm_output or {}
        usage = output.get("token_usage") or {}
        self.logger.info(
            "LLM call ok: model=%s duration=%s tokens=%s",
            output.get("model_name", "unknown"),
            "unknown" if elapsed is None else f"{elapsed:.0f}ms",
            usage.get("total_tokens", "unknown"),
        )

    def on_llm_error(self, error: BaseException, **kwargs: Any) -> None:
        from app.llm import describe_llm_error

        elapsed = self._elapsed_ms(kwargs.get("run_id"))
        failure = describe_llm_error(error)
        self.logger.error(
            "LLM call failed: %s after %s — %s",
            failure.summary(),
            "unknown" if elapsed is None else f"{elapsed:.0f}ms",
            failure.message,
        )


class LLMLoggingCallbackHandler(BaseCallbackHandler):
    """Callback handler for logging LLM interactions to file and logger."""

    def __init__(self) -> None:
        super().__init__()
        data_dir = config.get_data_dir()
        self.log_path = os.path.join(data_dir, "llm_interactions.log")
        # Ensure directory exists
        os.makedirs(data_dir, exist_ok=True)
        self.logger = logging.getLogger(__name__)

    def _write_log(self, entry: dict[str, Any]) -> None:
        """Write a JSON log entry to the file."""
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, default=str) + "\n")
        except Exception:
            self.logger.exception("Failed to write to LLM log file")

    def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[BaseMessage]],
        **kwargs: Any,
    ) -> None:
        """Run when LLM starts running."""
        model = serialized.get("name") or serialized.get("id") or "unknown"
        timestamp = datetime.now(UTC).isoformat()

        # Flatten messages for logging if multiple generations
        # Usually messages is [[System, User]] for a single generation
        flat_messages = [
            {"role": msg.type, "content": msg.content}
            for batch in messages
            for msg in batch
        ]

        entry = {
            "timestamp": timestamp,
            "event": "start",
            "model": model,
            "input_messages": flat_messages,
        }

        self.logger.info(f"LLM request started: {model}")
        self.logger.debug(f"LLM input: {json.dumps(entry, default=str)}")
        self._write_log(entry)

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        """Run when LLM ends running."""
        timestamp = datetime.now(UTC).isoformat()

        generations = [
            gen.text for gen_list in response.generations for gen in gen_list
        ]

        entry = {
            "timestamp": timestamp,
            "event": "end",
            "output_generations": generations,
            "llm_output": response.llm_output,  # Token usage often here
        }

        self.logger.info("LLM request finished")
        self.logger.debug(f"LLM output: {json.dumps(entry, default=str)}")
        self._write_log(entry)

    def on_llm_error(self, error: BaseException, **kwargs: Any) -> None:
        """Run when LLM errors."""
        timestamp = datetime.now(UTC).isoformat()
        entry = {
            "timestamp": timestamp,
            "event": "error",
            "error": str(error),
        }
        self.logger.error(f"LLM error: {error}")
        self._write_log(entry)
