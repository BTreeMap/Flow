"""Tests for the ConversationFlow orchestrator (§4.1, §2.2, §3.3, §8)."""

from __future__ import annotations

from app.engine.flow import (
    MAX_HISTORY_LENGTH,
    MAX_HISTORY_MESSAGES_FOR_LLM,
    ConversationFlow,
)
from app.engine.modules import (
    INTAKE_FALLBACK,
    IntakeModule,
    LLMResponse,
    StubLLMClient,
)
from app.engine.state import (
    ConversationHistory,
    ConversationMessage,
    ConversationState,
    DataKey,
)
from app.engine.tools import ToolCall, get_or_create_user_profile


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _empty_state() -> dict[str, str]:
    return {}


def _state_in_feedback() -> dict[str, str]:
    return {DataKey.CONVERSATION_STATE.value: ConversationState.FEEDBACK.value}


# ---------------------------------------------------------------------------
# Sub-state routing (§3.1, §4.1)
# ---------------------------------------------------------------------------


class TestSubStateRouting:
    def test_defaults_to_intake(self) -> None:
        """Empty state routes to INTAKE module."""
        flow = ConversationFlow()
        result = flow.process_response(_empty_state(), "user1", "hello")
        # StubLLMClient returns default text
        assert result  # non-empty response

    def test_feedback_routing(self) -> None:
        """State set to FEEDBACK routes to FeedbackModule."""
        flow = ConversationFlow()
        state = _state_in_feedback()
        result = flow.process_response(state, "user1", "I did my habit today")
        assert result  # non-empty response

    def test_feedback_cancels_pending_timers(self) -> None:
        """Processing in FEEDBACK clears feedback timer IDs (§4.3)."""
        flow = ConversationFlow()
        state = _state_in_feedback()
        state[DataKey.FEEDBACK_TIMER_ID.value] = "timer_abc"
        state[DataKey.FEEDBACK_FOLLOWUP_TIMER_ID.value] = "timer_xyz"

        flow.process_response(state, "user1", "update")
        assert state[DataKey.FEEDBACK_TIMER_ID.value] == ""
        assert state[DataKey.FEEDBACK_FOLLOWUP_TIMER_ID.value] == ""


# ---------------------------------------------------------------------------
# History trimming (§3.3)
# ---------------------------------------------------------------------------


class TestHistoryTrimming:
    def test_history_capped_at_50(self) -> None:
        """History is trimmed to MAX_HISTORY_LENGTH (50) on save."""
        flow = ConversationFlow()
        state = _empty_state()

        # Build a history with 55 messages already
        history = ConversationHistory(
            messages=[
                ConversationMessage(role="user", content=f"msg-{i}") for i in range(55)
            ]
        )
        state[DataKey.CONVERSATION_HISTORY.value] = history.model_dump_json()

        flow.process_response(state, "user1", "new message")

        # After processing, history should have at most MAX_HISTORY_LENGTH
        saved = ConversationHistory.model_validate_json(
            state[DataKey.CONVERSATION_HISTORY.value]
        )
        assert len(saved.messages) <= MAX_HISTORY_LENGTH

    def test_llm_sees_at_most_30_messages(self) -> None:
        """_get_chat_history returns at most 30 messages for LLM."""
        flow = ConversationFlow()
        history = ConversationHistory(
            messages=[
                ConversationMessage(role="user", content=f"msg-{i}") for i in range(45)
            ]
        )
        trimmed = flow._get_chat_history(history)
        assert len(trimmed) == MAX_HISTORY_MESSAGES_FOR_LLM

    def test_preserves_recent_messages(self) -> None:
        """Trimming keeps the most recent messages."""
        flow = ConversationFlow()
        state = _empty_state()

        history = ConversationHistory(
            messages=[
                ConversationMessage(role="user", content=f"msg-{i}") for i in range(55)
            ]
        )
        state[DataKey.CONVERSATION_HISTORY.value] = history.model_dump_json()

        flow.process_response(state, "user1", "latest")

        saved = ConversationHistory.model_validate_json(
            state[DataKey.CONVERSATION_HISTORY.value]
        )
        # The last message should be the assistant response
        assert saved.messages[-1].role == "assistant"
        # The second-to-last should be our "latest" user message
        assert saved.messages[-2].content == "latest"


# ---------------------------------------------------------------------------
# Tool loop behavior (§8.1)
# ---------------------------------------------------------------------------


class TestToolLoop:
    def test_terminates_on_content(self) -> None:
        """Tool loop ends when LLM returns content (§8.1)."""
        client = StubLLMClient(
            responses=[
                LLMResponse(
                    tool_calls=[
                        ToolCall(
                            id="tc1",
                            name="save_user_profile",
                            arguments={"prompt_anchor": "test"},
                        )
                    ]
                ),
                LLMResponse(content="Profile saved! Let's continue."),
            ]
        )
        module = IntakeModule(llm_client=client)
        result = module.execute(_empty_state(), "hello", [])
        assert result == "Profile saved! Let's continue."

    def test_max_10_rounds_fallback(self) -> None:
        """After 10 rounds of tool calls, returns fallback (§8.1)."""
        # Create 10 tool-only responses followed by nothing
        tool_responses = [
            LLMResponse(
                tool_calls=[
                    ToolCall(
                        id=f"tc{i}",
                        name="save_user_profile",
                        arguments={"additional_info": f"round {i}"},
                    )
                ]
            )
            for i in range(12)  # more than MAX_TOOL_ROUNDS
        ]
        client = StubLLMClient(responses=tool_responses)
        module = IntakeModule(llm_client=client)
        result = module.execute(_empty_state(), "hello", [])
        assert result == INTAKE_FALLBACK

    def test_fallback_on_empty_response(self) -> None:
        """No content and no tool calls returns fallback (§8.1)."""
        client = StubLLMClient(responses=[LLMResponse(content="", tool_calls=[])])
        module = IntakeModule(llm_client=client)
        result = module.execute(_empty_state(), "hello", [])
        assert result == INTAKE_FALLBACK

    def test_tool_error_continues_loop(self) -> None:
        """Tool errors are returned as strings; loop continues (§8.1, Scenario 10)."""
        client = StubLLMClient(
            responses=[
                LLMResponse(
                    tool_calls=[
                        ToolCall(
                            id="tc1",
                            name="nonexistent_tool",
                            arguments={},
                        )
                    ]
                ),
                LLMResponse(content="I encountered an error but recovered."),
            ]
        )
        module = IntakeModule(llm_client=client)
        result = module.execute(_empty_state(), "hello", [])
        assert result == "I encountered an error but recovered."


# ---------------------------------------------------------------------------
# Poll responses (§4.1)
# ---------------------------------------------------------------------------


class TestPollResponses:
    def test_done_increments_success_count(self) -> None:
        flow = ConversationFlow()
        state = _empty_state()
        flow.process_response(state, "user1", "Done")
        profile = get_or_create_user_profile(state)
        assert profile.success_count == 1

    def test_intensity_more(self) -> None:
        flow = ConversationFlow()
        state = _empty_state()
        flow.process_response(state, "user1", "more")
        profile = get_or_create_user_profile(state)
        assert profile.intensity == "high"

    def test_intensity_less(self) -> None:
        flow = ConversationFlow()
        state = _empty_state()
        flow.process_response(state, "user1", "less")
        profile = get_or_create_user_profile(state)
        assert profile.intensity == "low"

    def test_intensity_same(self) -> None:
        flow = ConversationFlow()
        state = _empty_state()
        flow.process_response(state, "user1", "same")
        profile = get_or_create_user_profile(state)
        assert profile.intensity == "normal"
