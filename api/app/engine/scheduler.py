"""Scheduling logic matching legacy §5 — daily prompts, reminders, auto-feedback."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from app.engine.state import (
    ConversationState,
    DailyPromptPendingState,
    DataKey,
    UserProfile,
)
from app.engine.tools import (
    StateData,
    _get_state,
    _set_state,
    execute_prompt_generator,
    get_or_create_user_profile,
)

# §5.2 — Default reminder delay
DEFAULT_DAILY_PROMPT_REMINDER_DELAY = timedelta(hours=5)

# §5.3 — Auto-feedback enforcement delay
AUTO_FEEDBACK_ENFORCEMENT_DELAY = timedelta(minutes=5)

# Default reminder message (§5.2, §10.2 — exact wording is incidental)
DEFAULT_REMINDER_MESSAGE = (
    "Friendly check-in: we haven't heard back after today's habit prompt. "
    "Reply with a quick update when you're ready!"
)


class OutboxEvent:
    """Represents a durable scheduled event stored in outbox_events table."""

    def __init__(
        self,
        event_id: str = "",
        participant_id: str = "",
        event_type: str = "",
        dedup_key: str = "",
        fire_at: datetime | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        self.event_id = event_id or uuid.uuid4().hex[:16]
        self.participant_id = participant_id
        self.event_type = event_type
        self.dedup_key = dedup_key
        self.fire_at = fire_at
        self.payload = payload or {}


class Scheduler:
    """Manages scheduled events (daily prompts, reminders, auto-feedback).

    Works on state dicts; outbox events are collected for persistence by the
    caller.  This keeps the engine decoupled from SQLAlchemy.
    """

    def __init__(
        self,
        reminder_delay: timedelta = DEFAULT_DAILY_PROMPT_REMINDER_DELAY,
        auto_feedback_enabled: bool = True,
    ) -> None:
        self.reminder_delay = reminder_delay
        self.auto_feedback_enabled = auto_feedback_enabled
        # Outbox accumulates events for the caller to persist
        self.pending_events: list[OutboxEvent] = []

    # ------------------------------------------------------------------
    # Daily prompt reminder (§5.2)
    # ------------------------------------------------------------------

    def schedule_daily_prompt_reminder(
        self,
        state_data: StateData,
        participant_id: str,
        sent_at: datetime,
        recipient: str = "",
    ) -> str:
        """Schedule a follow-up reminder after a daily prompt (§5.2).

        Returns the timer ID.
        """
        # Cancel any existing reminder (dedup)
        self._cancel_reminder(state_data, participant_id)

        reminder_due = sent_at + self.reminder_delay
        pending = DailyPromptPendingState(
            sent_at=sent_at,
            to=recipient,
            reminder_due_at=reminder_due,
        )
        _set_state(
            state_data,
            DataKey.DAILY_PROMPT_PENDING,
            pending.model_dump_json(),
        )

        timer_id = f"reminder_{uuid.uuid4().hex[:12]}"
        _set_state(state_data, DataKey.DAILY_PROMPT_REMINDER_TIMER_ID, timer_id)

        # Create outbox event for durable scheduling
        self.pending_events.append(
            OutboxEvent(
                participant_id=participant_id,
                event_type="daily_prompt_reminder",
                dedup_key=f"daily_prompt_reminder:{participant_id}",
                fire_at=reminder_due,
                payload={"sent_at": sent_at.isoformat(), "to": recipient},
            )
        )
        return timer_id

    def handle_daily_prompt_reply(
        self,
        state_data: StateData,
        participant_id: str,
        reply_timestamp: datetime | None = None,
    ) -> bool:
        """Cancel pending reminder when user replies (§5.2).

        Returns True if a pending reminder was cancelled.
        """
        raw = _get_state(state_data, DataKey.DAILY_PROMPT_PENDING)
        if not raw:
            return False

        try:
            pending = DailyPromptPendingState.model_validate_json(raw)
        except Exception:
            return False

        reply_ts = reply_timestamp or datetime.now(timezone.utc)

        # Validate reply timestamp > sent timestamp (§5.2)
        if reply_ts <= pending.sent_at:
            return False

        # Cancel timer/job
        self._cancel_reminder(state_data, participant_id)

        # Clear pending state
        _set_state(state_data, DataKey.DAILY_PROMPT_PENDING, "")

        # Record responded-at
        _set_state(
            state_data,
            DataKey.DAILY_PROMPT_RESPONDED_AT,
            reply_ts.isoformat(),
        )
        return True

    def _cancel_reminder(
        self, state_data: StateData, participant_id: str
    ) -> None:
        _set_state(state_data, DataKey.DAILY_PROMPT_REMINDER_TIMER_ID, "")

    # ------------------------------------------------------------------
    # Send daily prompt reminder (§5.2 — fires when timer elapses)
    # ------------------------------------------------------------------

    def send_daily_prompt_reminder(
        self,
        state_data: StateData,
        expected_sent_at: datetime,
    ) -> str | None:
        """Fire the reminder if the pending state still matches (§5.2).

        Returns the reminder message or None if stale.
        """
        raw = _get_state(state_data, DataKey.DAILY_PROMPT_PENDING)
        if not raw:
            return None

        try:
            pending = DailyPromptPendingState.model_validate_json(raw)
        except Exception:
            return None

        # Stale check
        if pending.sent_at != expected_sent_at:
            return None

        # Record reminder sent
        _set_state(
            state_data,
            DataKey.DAILY_PROMPT_REMINDER_SENT_AT,
            datetime.now(timezone.utc).isoformat(),
        )
        # Clear pending
        _set_state(state_data, DataKey.DAILY_PROMPT_PENDING, "")

        return DEFAULT_REMINDER_MESSAGE

    # ------------------------------------------------------------------
    # Auto-feedback enforcement (§5.3)
    # ------------------------------------------------------------------

    def schedule_auto_feedback_enforcement(
        self,
        state_data: StateData,
        participant_id: str,
    ) -> str | None:
        """Schedule 5-minute auto-feedback timer after a prompt (§5.3).

        Returns the timer ID or None if auto-feedback is disabled.
        """
        if not self.auto_feedback_enabled:
            return None

        # Cancel existing
        _set_state(state_data, DataKey.AUTO_FEEDBACK_TIMER_ID, "")

        timer_id = f"auto_feedback_{uuid.uuid4().hex[:12]}"
        _set_state(state_data, DataKey.AUTO_FEEDBACK_TIMER_ID, timer_id)

        fire_at = datetime.now(timezone.utc) + AUTO_FEEDBACK_ENFORCEMENT_DELAY
        self.pending_events.append(
            OutboxEvent(
                participant_id=participant_id,
                event_type="auto_feedback",
                dedup_key=f"auto_feedback:{participant_id}",
                fire_at=fire_at,
            )
        )
        return timer_id

    def enforce_feedback_if_no_response(
        self,
        state_data: StateData,
    ) -> bool:
        """Transition to FEEDBACK if no reply within enforcement window (§5.3).

        Returns True if transition occurred.
        """
        current = _get_state(
            state_data, DataKey.CONVERSATION_STATE, ConversationState.INTAKE.value
        )
        if current == ConversationState.FEEDBACK.value:
            return False

        # Check if a newer prompt was sent within ~4.5 minutes
        last_sent_raw = _get_state(state_data, DataKey.LAST_PROMPT_SENT_AT)
        if last_sent_raw:
            try:
                last_sent = datetime.fromisoformat(last_sent_raw)
                elapsed = datetime.now(timezone.utc) - last_sent
                if elapsed < timedelta(minutes=4, seconds=30):
                    return False
            except (ValueError, TypeError):
                pass

        _set_state(
            state_data,
            DataKey.CONVERSATION_STATE,
            ConversationState.FEEDBACK.value,
        )
        return True

    # ------------------------------------------------------------------
    # Execute scheduled prompt (§5.1)
    # ------------------------------------------------------------------

    def execute_scheduled_prompt(
        self,
        state_data: StateData,
        participant_id: str,
        recipient: str = "",
    ) -> str:
        """Generate and deliver a daily prompt (§5.1).

        Returns the generated prompt text.
        """
        # Generate prompt via PromptGeneratorTool
        result = execute_prompt_generator(
            state_data,
            {"delivery_mode": "scheduled"},
        )

        if result.startswith("error:"):
            return result

        # Record last prompt sent at
        now = datetime.now(timezone.utc)
        _set_state(state_data, DataKey.LAST_PROMPT_SENT_AT, now.isoformat())

        # Schedule reminder
        self.schedule_daily_prompt_reminder(
            state_data, participant_id, now, recipient
        )

        # Check intensity adjustment
        self.check_and_send_intensity_adjustment(state_data, participant_id)

        # Schedule auto-feedback enforcement
        if self.auto_feedback_enabled:
            self.schedule_auto_feedback_enforcement(state_data, participant_id)

        return result

    # ------------------------------------------------------------------
    # Intensity adjustment (§5.4 / Scenario 8)
    # ------------------------------------------------------------------

    def check_and_send_intensity_adjustment(
        self,
        state_data: StateData,
        participant_id: str,
    ) -> bool:
        """Send intensity poll at most once per day (§5.4, Scenario 8).

        Returns True if the poll was (would be) sent.
        """
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        last = _get_state(state_data, DataKey.LAST_INTENSITY_PROMPT_DATE)
        if last == today_str:
            return False

        _set_state(state_data, DataKey.LAST_INTENSITY_PROMPT_DATE, today_str)
        # In production this would send an intensity poll message
        return True
