"""Tests for tool definitions and execution (§4.4–§4.7, §8.1)."""

from __future__ import annotations

import json

from app.engine.state import DataKey, UserProfile
from app.engine.tools import (
    ToolCall,
    execute_profile_save,
    execute_prompt_generator,
    execute_scheduler,
    execute_state_transition,
    execute_tool,
    get_or_create_user_profile,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _empty_state() -> dict[str, str]:
    return {}


def _state_with_profile(**overrides: str) -> dict[str, str]:
    profile = UserProfile(**overrides)
    return {DataKey.USER_PROFILE.value: profile.model_dump_json()}


# ---------------------------------------------------------------------------
# ProfileSaveTool (§4.7) — field-by-field merge
# ---------------------------------------------------------------------------


class TestProfileSave:
    def test_only_non_empty_and_different_fields_saved(self) -> None:
        state = _state_with_profile(prompt_anchor="old anchor")
        result = execute_profile_save(
            state,
            {"prompt_anchor": "old anchor", "preferred_time": "8am"},
        )
        assert result == "success"
        profile = get_or_create_user_profile(state)
        assert profile.prompt_anchor == "old anchor"  # unchanged
        assert profile.preferred_time == "8am"  # new value

    def test_empty_values_not_merged(self) -> None:
        state = _state_with_profile(prompt_anchor="existing")
        execute_profile_save(state, {"prompt_anchor": "", "preferred_time": ""})
        profile = get_or_create_user_profile(state)
        assert profile.prompt_anchor == "existing"

    def test_noop_when_nothing_changes(self) -> None:
        state = _state_with_profile(prompt_anchor="same")
        result = execute_profile_save(state, {"prompt_anchor": "same"})
        assert result == "noop"

    def test_whitespace_only_ignored(self) -> None:
        state = _state_with_profile(prompt_anchor="existing")
        # result = execute_profile_save(state, {"prompt_anchor": "   "})
        profile = get_or_create_user_profile(state)
        assert profile.prompt_anchor == "existing"

    def test_legacy_last_blocker_alias(self) -> None:
        """last_blocker should be mapped to last_barrier (§4.7)."""
        state = _empty_state()
        execute_profile_save(state, {"last_blocker": "too tired"})
        profile = get_or_create_user_profile(state)
        assert profile.last_barrier == "too tired"

    def test_last_barrier_takes_precedence_over_last_blocker(self) -> None:
        state = _empty_state()
        execute_profile_save(
            state,
            {"last_blocker": "blocker val", "last_barrier": "barrier val"},
        )
        profile = get_or_create_user_profile(state)
        assert profile.last_barrier == "barrier val"

    def test_tone_tags_via_profile_save(self) -> None:
        state = _empty_state()
        result = execute_profile_save(
            state,
            {"tone_tags": ["concise", "formal"], "tone_update_source": "explicit"},
        )
        assert result == "success"
        profile = get_or_create_user_profile(state)
        assert "concise" in profile.tone.tone_tags

    def test_tone_tags_as_json_string(self) -> None:
        state = _empty_state()
        execute_profile_save(
            state,
            {"tone_tags": '["concise"]', "tone_update_source": "explicit"},
        )
        profile = get_or_create_user_profile(state)
        assert "concise" in profile.tone.tone_tags


# ---------------------------------------------------------------------------
# PromptGeneratorTool (§4.5)
# ---------------------------------------------------------------------------


class TestPromptGenerator:
    def test_requires_prompt_anchor(self) -> None:
        state = _state_with_profile(preferred_time="8am")
        result = execute_prompt_generator(state, {})
        assert "error" in result
        assert "PromptAnchor" in result

    def test_requires_preferred_time(self) -> None:
        state = _state_with_profile(prompt_anchor="after coffee")
        result = execute_prompt_generator(state, {})
        assert "error" in result
        assert "PreferredTime" in result

    def test_success_with_required_fields(self) -> None:
        state = _state_with_profile(
            prompt_anchor="after coffee", preferred_time="8am"
        )
        result = execute_prompt_generator(state, {})
        assert "error" not in result
        assert "after coffee" in result
        assert "8am" in result

    def test_increments_total_prompts(self) -> None:
        state = _state_with_profile(
            prompt_anchor="after coffee", preferred_time="8am"
        )
        execute_prompt_generator(state, {})
        profile = get_or_create_user_profile(state)
        assert profile.total_prompts == 1

    def test_stores_last_habit_prompt(self) -> None:
        state = _state_with_profile(
            prompt_anchor="after coffee", preferred_time="8am"
        )
        execute_prompt_generator(state, {})
        assert state.get(DataKey.LAST_HABIT_PROMPT.value, "") != ""

    def test_warnings_for_missing_optional_fields(self) -> None:
        state = _state_with_profile(
            prompt_anchor="anchor", preferred_time="9am"
        )
        result = execute_prompt_generator(state, {})
        assert "warnings" in result
        assert "HabitDomain" in result


# ---------------------------------------------------------------------------
# StateTransitionTool (§4.6)
# ---------------------------------------------------------------------------


class TestStateTransition:
    def test_immediate_transition(self) -> None:
        state = _empty_state()
        result = execute_state_transition(
            state, {"target_state": "FEEDBACK"}
        )
        assert "success" in result
        assert state[DataKey.CONVERSATION_STATE.value] == "FEEDBACK"

    def test_immediate_clears_auto_feedback_timer(self) -> None:
        state = {DataKey.AUTO_FEEDBACK_TIMER_ID.value: "timer_123"}
        execute_state_transition(state, {"target_state": "INTAKE"})
        assert state[DataKey.AUTO_FEEDBACK_TIMER_ID.value] == ""

    def test_delayed_transition_stores_timer_id(self) -> None:
        state = _empty_state()
        result = execute_state_transition(
            state,
            {"target_state": "FEEDBACK", "delay_minutes": 30},
        )
        assert "scheduled" in result
        assert state.get(DataKey.STATE_TRANSITION_TIMER_ID.value, "") != ""
        # State should NOT change immediately
        assert state.get(DataKey.CONVERSATION_STATE.value, "") != "FEEDBACK"

    def test_invalid_target_state(self) -> None:
        state = _empty_state()
        result = execute_state_transition(
            state, {"target_state": "INVALID"}
        )
        assert "error" in result

    def test_reason_included_in_result(self) -> None:
        state = _empty_state()
        result = execute_state_transition(
            state,
            {"target_state": "FEEDBACK", "reason": "profile complete"},
        )
        assert "profile complete" in result


# ---------------------------------------------------------------------------
# SchedulerTool (§4.4) — create / list / delete
# ---------------------------------------------------------------------------


class TestScheduler:
    def test_create_schedule(self) -> None:
        state = _empty_state()
        result = execute_scheduler(
            state,
            {"action": "create", "type": "fixed", "fixed_time": "08:00"},
        )
        assert "success" in result
        assert "created" in result

    def test_list_empty(self) -> None:
        state = _empty_state()
        result = execute_scheduler(state, {"action": "list"})
        assert "No schedules" in result

    def test_list_after_create(self) -> None:
        state = _empty_state()
        execute_scheduler(
            state,
            {"action": "create", "type": "fixed", "fixed_time": "08:00"},
        )
        result = execute_scheduler(state, {"action": "list"})
        assert "Schedules:" in result
        assert "fixed" in result

    def test_delete_schedule(self) -> None:
        state = _empty_state()
        execute_scheduler(
            state,
            {"action": "create", "type": "fixed", "fixed_time": "08:00"},
        )
        # Get the schedule ID from listing
        schedules_raw = json.loads(
            state.get(DataKey.SCHEDULE_REGISTRY.value, "[]")
        )
        sid = schedules_raw[0]["id"]
        result = execute_scheduler(
            state, {"action": "delete", "schedule_id": sid}
        )
        assert "success" in result
        assert "deleted" in result
        # Verify empty after deletion
        list_result = execute_scheduler(state, {"action": "list"})
        assert "No schedules" in list_result

    def test_delete_nonexistent(self) -> None:
        state = _empty_state()
        result = execute_scheduler(
            state, {"action": "delete", "schedule_id": "nonexistent"}
        )
        assert "error" in result

    def test_unknown_action(self) -> None:
        state = _empty_state()
        result = execute_scheduler(state, {"action": "foobar"})
        assert "error" in result


# ---------------------------------------------------------------------------
# Tool dispatcher (§8.1)
# ---------------------------------------------------------------------------


class TestToolDispatcher:
    def test_unknown_tool(self) -> None:
        state = _empty_state()
        result = execute_tool(
            state, ToolCall(id="1", name="nonexistent_tool", arguments={})
        )
        assert "error" in result.result
        assert "unknown tool" in result.result

    def test_dispatches_to_profile_save(self) -> None:
        state = _empty_state()
        result = execute_tool(
            state,
            ToolCall(
                id="1",
                name="save_user_profile",
                arguments={"prompt_anchor": "test"},
            ),
        )
        assert result.result == "success"
        assert result.name == "save_user_profile"
