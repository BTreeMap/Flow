"""Tests for LangChain @tool wrappers (§4.4–§4.7).

Validates:
- Each tool has a Pydantic args_schema
- Tools return typed result dicts
- Tools return structured errors on failure (no exceptions)
- Tool names and schemas match expectations
"""

from __future__ import annotations

from typing import Any

from app.engine.state import DataKey, UserProfile
from app.schemas.tool_schemas import (
    GenerateHabitPromptResult,
    ProfileSaveResult,
    SchedulerResult,
    StateTransitionResult,
)
from app.tools.langchain_tools import (
    make_feedback_tools,
    make_intake_tools,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _empty_state() -> dict[str, str]:
    return {}


def _state_with_profile(**overrides: str) -> dict[str, str]:
    profile = UserProfile(**overrides)
    return {DataKey.USER_PROFILE.value: profile.model_dump_json()}


def _find_tool(tools: list[Any], name: str) -> Any:
    for t in tools:
        if t.name == name:
            return t
    raise ValueError(f"Tool '{name}' not found in {[t.name for t in tools]}")


# ---------------------------------------------------------------------------
# Tool creation and schema validation
# ---------------------------------------------------------------------------


class TestToolCreation:
    def test_intake_tools_have_four_tools(self) -> None:
        tools = make_intake_tools(_empty_state())
        names = sorted(t.name for t in tools)
        assert names == [
            "generate_habit_prompt",
            "save_user_profile",
            "scheduler",
            "transition_state",
        ]

    def test_feedback_tools_have_three_tools(self) -> None:
        tools = make_feedback_tools(_empty_state())
        names = sorted(t.name for t in tools)
        assert names == [
            "save_user_profile",
            "scheduler",
            "transition_state",
        ]

    def test_feedback_tools_exclude_prompt_generator(self) -> None:
        """Feedback agent must NOT have generate_habit_prompt (§4.3)."""
        tools = make_feedback_tools(_empty_state())
        names = [t.name for t in tools]
        assert "generate_habit_prompt" not in names

    def test_all_tools_have_args_schema(self) -> None:
        """Every tool must declare a Pydantic args_schema."""
        for t in make_intake_tools(_empty_state()):
            assert t.args_schema is not None
            assert hasattr(t.args_schema, "model_fields")


# ---------------------------------------------------------------------------
# save_user_profile tool
# ---------------------------------------------------------------------------


class TestProfileSaveTool:
    def test_success_returns_typed_result(self) -> None:
        state = _empty_state()
        tools = make_intake_tools(state)
        tool = _find_tool(tools, "save_user_profile")
        result = tool.invoke({"prompt_anchor": "after coffee"})
        parsed = ProfileSaveResult.model_validate(result)
        assert parsed.ok is True
        assert parsed.status == "success"

    def test_noop_returns_typed_result(self) -> None:
        state = _state_with_profile(prompt_anchor="same")
        tools = make_intake_tools(state)
        tool = _find_tool(tools, "save_user_profile")
        result = tool.invoke({"prompt_anchor": "same"})
        parsed = ProfileSaveResult.model_validate(result)
        assert parsed.ok is True
        assert parsed.status == "noop"

    def test_empty_args_returns_noop(self) -> None:
        state = _empty_state()
        tools = make_intake_tools(state)
        tool = _find_tool(tools, "save_user_profile")
        result = tool.invoke({})
        parsed = ProfileSaveResult.model_validate(result)
        assert parsed.ok is True
        assert parsed.status == "noop"


# ---------------------------------------------------------------------------
# scheduler tool
# ---------------------------------------------------------------------------


class TestSchedulerTool:
    def test_create_returns_typed_result(self) -> None:
        state = _empty_state()
        tools = make_intake_tools(state)
        tool = _find_tool(tools, "scheduler")
        result = tool.invoke({"action": "create", "type": "fixed", "fixed_time": "08:00"})
        parsed = SchedulerResult.model_validate(result)
        assert parsed.ok is True
        assert "created" in parsed.message

    def test_list_empty_returns_typed_result(self) -> None:
        state = _empty_state()
        tools = make_intake_tools(state)
        tool = _find_tool(tools, "scheduler")
        result = tool.invoke({"action": "list"})
        parsed = SchedulerResult.model_validate(result)
        assert parsed.ok is True

    def test_unknown_action_returns_error(self) -> None:
        state = _empty_state()
        tools = make_intake_tools(state)
        tool = _find_tool(tools, "scheduler")
        result = tool.invoke({"action": "delete", "schedule_id": "nonexistent"})
        parsed = SchedulerResult.model_validate(result)
        assert parsed.ok is False
        assert parsed.error is not None


# ---------------------------------------------------------------------------
# generate_habit_prompt tool
# ---------------------------------------------------------------------------


class TestPromptGeneratorTool:
    def test_missing_profile_returns_error(self) -> None:
        state = _empty_state()
        tools = make_intake_tools(state)
        tool = _find_tool(tools, "generate_habit_prompt")
        result = tool.invoke({})
        parsed = GenerateHabitPromptResult.model_validate(result)
        assert parsed.ok is False
        assert parsed.error is not None

    def test_success_with_complete_profile(self) -> None:
        state = _state_with_profile(
            prompt_anchor="after coffee", preferred_time="8am"
        )
        tools = make_intake_tools(state)
        tool = _find_tool(tools, "generate_habit_prompt")
        result = tool.invoke({})
        parsed = GenerateHabitPromptResult.model_validate(result)
        assert parsed.ok is True
        assert parsed.prompt is not None
        assert "after coffee" in parsed.prompt


# ---------------------------------------------------------------------------
# transition_state tool
# ---------------------------------------------------------------------------


class TestStateTransitionTool:
    def test_immediate_transition(self) -> None:
        state = _empty_state()
        tools = make_intake_tools(state)
        tool = _find_tool(tools, "transition_state")
        result = tool.invoke({"target_state": "FEEDBACK"})
        parsed = StateTransitionResult.model_validate(result)
        assert parsed.ok is True
        assert parsed.applied_state == "FEEDBACK"
        assert state[DataKey.CONVERSATION_STATE.value] == "FEEDBACK"

    def test_delayed_transition(self) -> None:
        state = _empty_state()
        tools = make_intake_tools(state)
        tool = _find_tool(tools, "transition_state")
        result = tool.invoke({
            "target_state": "FEEDBACK",
            "delay_minutes": 30,
        })
        parsed = StateTransitionResult.model_validate(result)
        assert parsed.ok is True
        assert parsed.scheduled_for is not None

    def test_invalid_state_returns_error(self) -> None:
        """Invalid target_state is caught by Pydantic schema validation."""
        import pytest
        from pydantic import ValidationError

        state = _empty_state()
        tools = make_intake_tools(state)
        tool = _find_tool(tools, "transition_state")
        # Pydantic Literal["INTAKE", "FEEDBACK"] rejects "INVALID"
        with pytest.raises(ValidationError):
            tool.invoke({"target_state": "INVALID"})
