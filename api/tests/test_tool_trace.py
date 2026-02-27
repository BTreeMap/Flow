"""Tests for the ToolCallTraceHandler callback."""

from __future__ import annotations

import uuid

from app.agents.tool_trace import ToolCallTraceHandler, _safe_json_parse, _truncate


class TestSafeJsonParse:
    def test_valid_json_string(self) -> None:
        result = _safe_json_parse('{"key": "value"}')
        assert result == {"key": "value"}

    def test_invalid_json_string(self) -> None:
        result = _safe_json_parse("not json")
        assert result == "not json"

    def test_non_string_passthrough(self) -> None:
        result = _safe_json_parse({"already": "dict"})
        assert result == {"already": "dict"}

    def test_int_passthrough(self) -> None:
        result = _safe_json_parse(42)
        assert result == 42


class TestTruncate:
    def test_short_value(self) -> None:
        result = _truncate("short")
        assert result == "short"

    def test_long_value(self) -> None:
        result = _truncate("x" * 3000, limit=100)
        assert isinstance(result, str)
        assert len(result) <= 101  # 100 + ellipsis char
        assert result.endswith("…")


class TestToolCallTraceHandler:
    def test_records_tool_start(self) -> None:
        handler = ToolCallTraceHandler()
        run_id = uuid.uuid4()
        handler.on_tool_start(
            serialized={"name": "my_tool"},
            input_str='{"arg1": "val1"}',
            run_id=run_id,
        )
        calls = handler.get_tool_calls()
        assert len(calls) == 1
        assert calls[0]["tool"] == "my_tool"
        assert calls[0]["args"] == {"arg1": "val1"}
        assert calls[0]["run_id"] == str(run_id)

    def test_records_tool_end(self) -> None:
        handler = ToolCallTraceHandler()
        run_id = uuid.uuid4()
        handler.on_tool_start(
            serialized={"name": "tool_a"},
            input_str="plain text arg",
            run_id=run_id,
        )
        handler.on_tool_end(output="result text", run_id=run_id)
        calls = handler.get_tool_calls()
        assert calls[0]["output"] == "result text"

    def test_records_tool_error(self) -> None:
        handler = ToolCallTraceHandler()
        run_id = uuid.uuid4()
        handler.on_tool_start(
            serialized={"name": "tool_b"},
            input_str="{}",
            run_id=run_id,
        )
        handler.on_tool_error(error=ValueError("boom"), run_id=run_id)
        calls = handler.get_tool_calls()
        assert "boom" in calls[0]["error"]

    def test_chronological_order(self) -> None:
        handler = ToolCallTraceHandler()
        for i in range(3):
            handler.on_tool_start(
                serialized={"name": f"tool_{i}"},
                input_str="{}",
                run_id=uuid.uuid4(),
            )
        calls = handler.get_tool_calls()
        assert [c["tool"] for c in calls] == ["tool_0", "tool_1", "tool_2"]

    def test_get_tool_calls_returns_copy(self) -> None:
        handler = ToolCallTraceHandler()
        handler.on_tool_start(
            serialized={"name": "t"},
            input_str="{}",
            run_id=uuid.uuid4(),
        )
        calls1 = handler.get_tool_calls()
        calls2 = handler.get_tool_calls()
        assert calls1 == calls2
        assert calls1 is not calls2

    def test_missing_run_id_on_end_is_safe(self) -> None:
        handler = ToolCallTraceHandler()
        # on_tool_end without a matching on_tool_start should not raise
        handler.on_tool_end(output="orphan", run_id=uuid.uuid4())
        assert handler.get_tool_calls() == []
