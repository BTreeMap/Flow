"""ConversationFlow orchestrator matching legacy §4.1, §2.2."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from app.engine.modules import FeedbackModule, IntakeModule, LLMClient, StubLLMClient
from app.engine.scheduler import Scheduler
from app.engine.state import (
    ConversationHistory,
    ConversationMessage,
    ConversationState,
    DataKey,
    TOP_LEVEL_STATE,
    UserProfile,
)
from app.engine.tools import (
    StateData,
    _get_state,
    _set_state,
    get_or_create_user_profile,
)

# §3.3 — History limits
MAX_HISTORY_LENGTH = 50
MAX_HISTORY_MESSAGES_FOR_LLM = 30


class ConversationFlow:
    """Orchestrator — routes messages to IntakeModule or FeedbackModule (§4.1).

    Works entirely on a ``state_data`` dict (``dict[str, str]``), decoupled
    from any persistence layer.
    """

    def __init__(
        self,
        intake_module: IntakeModule | None = None,
        feedback_module: FeedbackModule | None = None,
        scheduler: Scheduler | None = None,
        llm_client: LLMClient | None = None,
    ) -> None:
        llm = llm_client or StubLLMClient()
        self.intake_module = intake_module or IntakeModule(llm_client=llm)
        self.feedback_module = feedback_module or FeedbackModule(llm_client=llm)
        self.scheduler = scheduler or Scheduler()

    # ------------------------------------------------------------------
    # Public entry point (§4.1)
    # ------------------------------------------------------------------

    def process_response(
        self,
        state_data: StateData,
        participant_id: str,
        user_message: str,
    ) -> str:
        """Process an incoming user message (§2.2 step 3-4).

        1. Get history → append user msg
        2. Check polls (Done / intensity)
        3. Handle reminder reply
        4. Route by sub-state
        5. Append assistant → save history
        """
        history = self._get_conversation_history(state_data)
        now = datetime.now(timezone.utc)

        # Append user message
        history.messages.append(
            ConversationMessage(role="user", content=user_message, timestamp=now)
        )

        # Check for "Done" poll response → increment SuccessCount
        if user_message.strip().lower() == "done":
            profile = get_or_create_user_profile(state_data)
            profile.success_count += 1
            _set_state(
                state_data,
                DataKey.USER_PROFILE,
                profile.model_dump_json(),
            )

        # Check for intensity-adjustment poll response
        if user_message.strip().lower() in ("more", "less", "same"):
            profile = get_or_create_user_profile(state_data)
            mapping = {"more": "high", "less": "low", "same": "normal"}
            profile.intensity = mapping.get(
                user_message.strip().lower(), profile.intensity
            )
            _set_state(
                state_data,
                DataKey.USER_PROFILE,
                profile.model_dump_json(),
            )

        # Handle daily prompt reply — cancel pending reminders (§5.2)
        self.scheduler.handle_daily_prompt_reply(
            state_data, participant_id, reply_timestamp=now
        )

        # Route by sub-state (§3.1 critical invariant)
        sub_state = self._get_conversation_state(state_data)

        if sub_state == ConversationState.FEEDBACK:
            assistant_text = self._process_feedback_state(
                state_data, user_message, history
            )
        else:
            assistant_text = self._process_intake_state(
                state_data, user_message, history
            )

        # Append assistant response
        history.messages.append(
            ConversationMessage(
                role="assistant", content=assistant_text, timestamp=datetime.now(timezone.utc)
            )
        )

        # Save history (trimmed to max 50)
        self._save_conversation_history(state_data, history)

        return assistant_text

    # ------------------------------------------------------------------
    # Sub-state routing (§4.1)
    # ------------------------------------------------------------------

    def _process_intake_state(
        self,
        state_data: StateData,
        user_message: str,
        history: ConversationHistory,
    ) -> str:
        """Route to IntakeModule (§2.2 step 5)."""
        chat_history = self._get_chat_history(history)
        return self.intake_module.execute(state_data, user_message, chat_history)

    def _process_feedback_state(
        self,
        state_data: StateData,
        user_message: str,
        history: ConversationHistory,
    ) -> str:
        """Route to FeedbackModule, then cancel pending feedback (§2.2 step 6)."""
        chat_history = self._get_chat_history(history)
        result = self.feedback_module.execute(state_data, user_message, chat_history)
        # Cancel pending feedback timers after processing (§4.3)
        self.feedback_module.cancel_pending_feedback(state_data)
        return result

    # ------------------------------------------------------------------
    # State helpers
    # ------------------------------------------------------------------

    def _get_conversation_state(self, state_data: StateData) -> ConversationState:
        """Get sub-state, defaulting to INTAKE (§3.1)."""
        raw = _get_state(state_data, DataKey.CONVERSATION_STATE, "")
        if raw == ConversationState.FEEDBACK.value:
            return ConversationState.FEEDBACK
        return ConversationState.INTAKE

    # ------------------------------------------------------------------
    # History management (§3.3)
    # ------------------------------------------------------------------

    def _get_conversation_history(self, state_data: StateData) -> ConversationHistory:
        raw = _get_state(state_data, DataKey.CONVERSATION_HISTORY, "")
        if raw:
            try:
                return ConversationHistory.model_validate_json(raw)
            except Exception:
                pass
        return ConversationHistory()

    def _save_conversation_history(
        self,
        state_data: StateData,
        history: ConversationHistory,
    ) -> None:
        """Trim to MAX_HISTORY_LENGTH and persist (§3.3)."""
        if len(history.messages) > MAX_HISTORY_LENGTH:
            history.messages = history.messages[-MAX_HISTORY_LENGTH:]
        _set_state(
            state_data,
            DataKey.CONVERSATION_HISTORY,
            history.model_dump_json(),
        )

    def _get_chat_history(
        self,
        history: ConversationHistory,
    ) -> list[ConversationMessage]:
        """Return most recent messages for LLM context (§3.3)."""
        return history.messages[-MAX_HISTORY_MESSAGES_FOR_LLM:]
