"""LangChain callback handler that records tool calls in chronological order."""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler

logger = logging.getLogger(__name__)

_MAX_OUTPUT_CHARS = 2000


def _safe_json_parse(value: Any) -> Any:
    """Try to parse a JSON string into an object; return as-is on failure."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, ValueError):
            return value
    return value


def _truncate(value: Any, limit: int = _MAX_OUTPUT_CHARS) -> Any:
    """Truncate a value to *limit* characters for safe serialization."""
    try:
        text = json.dumps(value, default=str)
    except (TypeError, ValueError):
        text = str(value)
    if len(text) > limit:
        return text[:limit] + "…"
    return value


class ToolCallTraceHandler(BaseCallbackHandler):
    """Record tool invocations made during an agent run.

    Usage::

        handler = ToolCallTraceHandler()
        # pass as callback to LangGraph config
        result = agent.ainvoke(..., config={"callbacks": [handler]})
        tool_calls = handler.get_tool_calls()
    """

    def __init__(self) -> None:
        super().__init__()
        self._calls: list[dict[str, Any]] = []
        self._index: dict[str, int] = {}  # run_id -> index in _calls

    # -- lifecycle hooks ---------------------------------------------------

    def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        inputs: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        args = _safe_json_parse(input_str)
        entry: dict[str, Any] = {
            "tool": serialized.get("name", "unknown"),
            "args": args,
            "run_id": str(run_id),
        }
        idx = len(self._calls)
        self._calls.append(entry)
        self._index[str(run_id)] = idx

    def on_tool_end(
        self,
        output: str,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        idx = self._index.get(str(run_id))
        if idx is not None:
            self._calls[idx]["output"] = _truncate(output)

    def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        idx = self._index.get(str(run_id))
        if idx is not None:
            self._calls[idx]["error"] = str(error)[:_MAX_OUTPUT_CHARS]

    # -- public API --------------------------------------------------------

    def get_tool_calls(self) -> list[dict[str, Any]]:
        """Return the chronologically ordered list of tool call records."""
        return list(self._calls)
