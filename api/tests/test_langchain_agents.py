"""Tests for LangChain agent definitions and orchestrator pipeline.

Validates:
- Intake agent only gets intake tools
- Feedback agent only gets feedback tools
- Orchestrator processes turns with correct routing
- History trimming is preserved
- Poll responses are handled
- Feedback timer cancellation works
"""

from __future__ import annotations

from app.agents.orchestrator import (
    _get_sub_state,
    _handle_poll_responses,
    _load_history,
    _save_history,
    process_turn,
)
from app.engine.state import (
    ConversationHistory,
    ConversationMessage,
    ConversationState,
    DataKey,
    UserProfile,
)
from app.engine.tools import get_or_create_user_profile
from app.tools.langchain_tools import make_feedback_tools, make_intake_tools


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _empty_state() -> dict[str, str]:
    return {}


def _state_in_feedback() -> dict[str, str]:
    return {DataKey.CONVERSATION_STATE.value: ConversationState.FEEDBACK.value}


# ---------------------------------------------------------------------------
# Agent tool permissions
# ---------------------------------------------------------------------------


class TestAgentToolPermissions:
    def test_intake_agent_has_four_tools(self) -> None:
        tools = make_intake_tools(_empty_state())
        names = {t.name for t in tools}
        assert names == {
            "save_user_profile",
            "scheduler",
            "generate_habit_prompt",
            "transition_state",
        }

    def test_feedback_agent_has_three_tools(self) -> None:
        tools = make_feedback_tools(_empty_state())
        names = {t.name for t in tools}
        assert names == {
            "save_user_profile",
            "scheduler",
            "transition_state",
        }

    def test_feedback_agent_cannot_generate_prompts(self) -> None:
        """§4.3: Feedback module does not have generate_habit_prompt."""
        tools = make_feedback_tools(_empty_state())
        names = [t.name for t in tools]
        assert "generate_habit_prompt" not in names

    def test_intake_agent_has_prompt_generator(self) -> None:
        """§4.2: Intake module has generate_habit_prompt."""
        tools = make_intake_tools(_empty_state())
        names = [t.name for t in tools]
        assert "generate_habit_prompt" in names


# ---------------------------------------------------------------------------
# Orchestrator sub-state helpers
# ---------------------------------------------------------------------------


class TestSubStateHelper:
    def test_empty_state_returns_intake(self) -> None:
        assert _get_sub_state(_empty_state()) == "INTAKE"

    def test_feedback_state(self) -> None:
        assert _get_sub_state(_state_in_feedback()) == "FEEDBACK"

    def test_unknown_state_defaults_to_intake(self) -> None:
        state = {DataKey.CONVERSATION_STATE.value: "BOGUS"}
        assert _get_sub_state(state) == "INTAKE"


# ---------------------------------------------------------------------------
# Poll response handling
# ---------------------------------------------------------------------------


class TestPollResponses:
    def test_done_increments_success_count(self) -> None:
        state = _empty_state()
        _handle_poll_responses(state, "Done")
        profile = get_or_create_user_profile(state)
        assert profile.success_count == 1

    def test_more_sets_high_intensity(self) -> None:
        state = _empty_state()
        _handle_poll_responses(state, "more")
        profile = get_or_create_user_profile(state)
        assert profile.intensity == "high"

    def test_less_sets_low_intensity(self) -> None:
        state = _empty_state()
        _handle_poll_responses(state, "less")
        profile = get_or_create_user_profile(state)
        assert profile.intensity == "low"

    def test_same_sets_normal_intensity(self) -> None:
        state = _empty_state()
        _handle_poll_responses(state, "same")
        profile = get_or_create_user_profile(state)
        assert profile.intensity == "normal"


# ---------------------------------------------------------------------------
# History management
# ---------------------------------------------------------------------------


class TestHistoryManagement:
    def test_load_empty_history(self) -> None:
        history = _load_history(_empty_state())
        assert len(history.messages) == 0

    def test_save_trims_to_50(self) -> None:
        state = _empty_state()
        history = ConversationHistory(
            messages=[
                ConversationMessage(role="user", content=f"msg-{i}")
                for i in range(55)
            ]
        )
        _save_history(state, history)
        loaded = _load_history(state)
        assert len(loaded.messages) == 50

    def test_save_preserves_recent(self) -> None:
        state = _empty_state()
        history = ConversationHistory(
            messages=[
                ConversationMessage(role="user", content=f"msg-{i}")
                for i in range(55)
            ]
        )
        _save_history(state, history)
        loaded = _load_history(state)
        assert loaded.messages[-1].content == "msg-54"


# ---------------------------------------------------------------------------
# End-to-end orchestrator (no LLM — deterministic routing + stub modules)
# ---------------------------------------------------------------------------


class TestOrchestratorNoLLM:
    def test_intake_route_default(self) -> None:
        """With no LLM, empty state routes to INTAKE and returns text."""
        state = _empty_state()
        text, decision = process_turn(state, "user1", "hello")
        assert decision.route == "INTAKE"
        assert text  # non-empty assistant response

    def test_feedback_route_when_state_is_feedback(self) -> None:
        """With no LLM, FEEDBACK sub-state routes to FEEDBACK."""
        state = _state_in_feedback()
        text, decision = process_turn(state, "user1", "I did it")
        assert decision.route == "FEEDBACK"
        assert text

    def test_feedback_cancels_timers(self) -> None:
        """FEEDBACK processing clears feedback timer IDs (§4.3)."""
        state = _state_in_feedback()
        state[DataKey.FEEDBACK_TIMER_ID.value] = "timer_abc"
        state[DataKey.FEEDBACK_FOLLOWUP_TIMER_ID.value] = "timer_xyz"

        process_turn(state, "user1", "update")
        assert state[DataKey.FEEDBACK_TIMER_ID.value] == ""
        assert state[DataKey.FEEDBACK_FOLLOWUP_TIMER_ID.value] == ""

    def test_history_appended_and_saved(self) -> None:
        """User and assistant messages are appended to history."""
        state = _empty_state()
        process_turn(state, "user1", "hello there")
        history = _load_history(state)
        assert len(history.messages) >= 2
        assert history.messages[-2].role == "user"
        assert history.messages[-2].content == "hello there"
        assert history.messages[-1].role == "assistant"

    def test_done_poll_increments_success(self) -> None:
        state = _empty_state()
        process_turn(state, "user1", "Done")
        profile = get_or_create_user_profile(state)
        assert profile.success_count == 1

    def test_intensity_poll_more(self) -> None:
        state = _empty_state()
        process_turn(state, "user1", "more")
        profile = get_or_create_user_profile(state)
        assert profile.intensity == "high"

    def test_route_decision_returned(self) -> None:
        """process_turn returns the RouteDecision object."""
        state = _empty_state()
        _, decision = process_turn(state, "user1", "hi")
        assert decision.route in ("INTAKE", "FEEDBACK")
        assert hasattr(decision, "reason")
