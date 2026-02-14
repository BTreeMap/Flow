"""Tests for scheduling logic (§5 — daily prompts, reminders, auto-feedback)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.engine.scheduler import (
    AUTO_FEEDBACK_ENFORCEMENT_DELAY,
    DEFAULT_DAILY_PROMPT_REMINDER_DELAY,
    DEFAULT_REMINDER_MESSAGE,
    Scheduler,
)
from app.engine.state import (
    ConversationState,
    DailyPromptPendingState,
    DataKey,
    UserProfile,
)
from app.engine.tools import _get_state, get_or_create_user_profile


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _empty_state() -> dict[str, str]:
    return {}


def _state_with_profile(**overrides: str) -> dict[str, str]:
    profile = UserProfile(**overrides)
    return {DataKey.USER_PROFILE.value: profile.model_dump_json()}


# ---------------------------------------------------------------------------
# §5.2 — Daily prompt reminder scheduling (Scenario 6)
# ---------------------------------------------------------------------------


class TestDailyPromptReminder:
    def test_schedule_creates_pending_state(self) -> None:
        scheduler = Scheduler()
        state = _empty_state()
        now = datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc)

        timer_id = scheduler.schedule_daily_prompt_reminder(
            state, "user1", sent_at=now
        )
        assert timer_id
        assert state.get(DataKey.DAILY_PROMPT_REMINDER_TIMER_ID.value) == timer_id
        assert state.get(DataKey.DAILY_PROMPT_PENDING.value, "") != ""

    def test_schedule_creates_outbox_event(self) -> None:
        scheduler = Scheduler()
        state = _empty_state()
        now = datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc)

        scheduler.schedule_daily_prompt_reminder(state, "user1", sent_at=now)
        assert len(scheduler.pending_events) == 1
        event = scheduler.pending_events[0]
        assert event.event_type == "daily_prompt_reminder"
        assert event.dedup_key == "daily_prompt_reminder:user1"
        assert event.fire_at == now + DEFAULT_DAILY_PROMPT_REMINDER_DELAY

    def test_reminder_due_at_is_5_hours(self) -> None:
        scheduler = Scheduler()
        state = _empty_state()
        now = datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc)

        scheduler.schedule_daily_prompt_reminder(state, "user1", sent_at=now)
        pending = DailyPromptPendingState.model_validate_json(
            state[DataKey.DAILY_PROMPT_PENDING.value]
        )
        assert pending.reminder_due_at == now + timedelta(hours=5)


# ---------------------------------------------------------------------------
# §5.2 — Cancellation on user reply (Scenario 6)
# ---------------------------------------------------------------------------


class TestCancellationOnReply:
    def test_reply_cancels_pending_reminder(self) -> None:
        scheduler = Scheduler()
        state = _empty_state()
        sent = datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        reply = sent + timedelta(hours=1)

        scheduler.schedule_daily_prompt_reminder(state, "user1", sent_at=sent)
        cancelled = scheduler.handle_daily_prompt_reply(
            state, "user1", reply_timestamp=reply
        )
        assert cancelled is True
        assert state.get(DataKey.DAILY_PROMPT_PENDING.value) == ""
        assert state.get(DataKey.DAILY_PROMPT_REMINDER_TIMER_ID.value) == ""
        assert state.get(DataKey.DAILY_PROMPT_RESPONDED_AT.value, "") != ""

    def test_reply_before_sent_at_rejected(self) -> None:
        scheduler = Scheduler()
        state = _empty_state()
        sent = datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        reply = sent - timedelta(minutes=5)

        scheduler.schedule_daily_prompt_reminder(state, "user1", sent_at=sent)
        cancelled = scheduler.handle_daily_prompt_reply(
            state, "user1", reply_timestamp=reply
        )
        assert cancelled is False

    def test_no_pending_state_returns_false(self) -> None:
        scheduler = Scheduler()
        state = _empty_state()
        now = datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        cancelled = scheduler.handle_daily_prompt_reply(
            state, "user1", reply_timestamp=now
        )
        assert cancelled is False

    def test_late_reply_after_reminder_fired(self) -> None:
        """Scenario 7: Reminder fires, clears pending. Late reply finds nothing."""
        scheduler = Scheduler()
        state = _empty_state()
        sent = datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc)

        scheduler.schedule_daily_prompt_reminder(state, "user1", sent_at=sent)

        # Simulate reminder firing
        msg = scheduler.send_daily_prompt_reminder(state, expected_sent_at=sent)
        assert msg == DEFAULT_REMINDER_MESSAGE

        # Now the user replies late — pending is already cleared
        reply = sent + timedelta(hours=6)
        cancelled = scheduler.handle_daily_prompt_reply(
            state, "user1", reply_timestamp=reply
        )
        assert cancelled is False


# ---------------------------------------------------------------------------
# §5.2 — Send daily prompt reminder
# ---------------------------------------------------------------------------


class TestSendReminder:
    def test_stale_sent_at_returns_none(self) -> None:
        scheduler = Scheduler()
        state = _empty_state()
        sent = datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        scheduler.schedule_daily_prompt_reminder(state, "user1", sent_at=sent)

        # Try with wrong expected_sent_at
        wrong = datetime(2025, 6, 1, 11, 0, 0, tzinfo=timezone.utc)
        msg = scheduler.send_daily_prompt_reminder(state, expected_sent_at=wrong)
        assert msg is None

    def test_clears_pending_on_fire(self) -> None:
        scheduler = Scheduler()
        state = _empty_state()
        sent = datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        scheduler.schedule_daily_prompt_reminder(state, "user1", sent_at=sent)

        scheduler.send_daily_prompt_reminder(state, expected_sent_at=sent)
        assert state.get(DataKey.DAILY_PROMPT_PENDING.value) == ""
        assert state.get(DataKey.DAILY_PROMPT_REMINDER_SENT_AT.value, "") != ""


# ---------------------------------------------------------------------------
# §5.3 — Auto-feedback enforcement (Scenario 11)
# ---------------------------------------------------------------------------


class TestAutoFeedbackEnforcement:
    def test_schedule_creates_timer_and_event(self) -> None:
        scheduler = Scheduler(auto_feedback_enabled=True)
        state = _empty_state()
        timer_id = scheduler.schedule_auto_feedback_enforcement(state, "user1")
        assert timer_id is not None
        assert state[DataKey.AUTO_FEEDBACK_TIMER_ID.value] == timer_id
        assert len(scheduler.pending_events) == 1
        event = scheduler.pending_events[0]
        assert event.event_type == "auto_feedback"
        assert event.dedup_key == "auto_feedback:user1"

    def test_disabled_returns_none(self) -> None:
        scheduler = Scheduler(auto_feedback_enabled=False)
        state = _empty_state()
        timer_id = scheduler.schedule_auto_feedback_enforcement(state, "user1")
        assert timer_id is None

    def test_enforce_transitions_to_feedback(self) -> None:
        scheduler = Scheduler()
        state = {DataKey.CONVERSATION_STATE.value: ConversationState.INTAKE.value}
        # Set last prompt sent > 4.5 minutes ago
        old_time = (
            datetime.now(timezone.utc) - timedelta(minutes=5)
        ).isoformat()
        state[DataKey.LAST_PROMPT_SENT_AT.value] = old_time

        transitioned = scheduler.enforce_feedback_if_no_response(state)
        assert transitioned is True
        assert (
            state[DataKey.CONVERSATION_STATE.value]
            == ConversationState.FEEDBACK.value
        )

    def test_already_in_feedback_skips(self) -> None:
        scheduler = Scheduler()
        state = {
            DataKey.CONVERSATION_STATE.value: ConversationState.FEEDBACK.value
        }
        transitioned = scheduler.enforce_feedback_if_no_response(state)
        assert transitioned is False

    def test_recent_prompt_skips_enforcement(self) -> None:
        """If a newer prompt was sent within ~4.5 minutes, skip (§5.3)."""
        scheduler = Scheduler()
        state = {DataKey.CONVERSATION_STATE.value: ConversationState.INTAKE.value}
        recent = (
            datetime.now(timezone.utc) - timedelta(minutes=2)
        ).isoformat()
        state[DataKey.LAST_PROMPT_SENT_AT.value] = recent

        transitioned = scheduler.enforce_feedback_if_no_response(state)
        assert transitioned is False


# ---------------------------------------------------------------------------
# §5.4 / Scenario 8 — Intensity adjustment once per day
# ---------------------------------------------------------------------------


class TestIntensityAdjustment:
    def test_first_time_sends_poll(self) -> None:
        scheduler = Scheduler()
        state = _empty_state()
        sent = scheduler.check_and_send_intensity_adjustment(state, "user1")
        assert sent is True
        assert state.get(DataKey.LAST_INTENSITY_PROMPT_DATE.value, "") != ""

    def test_second_call_same_day_skips(self) -> None:
        scheduler = Scheduler()
        state = _empty_state()
        scheduler.check_and_send_intensity_adjustment(state, "user1")
        sent = scheduler.check_and_send_intensity_adjustment(state, "user1")
        assert sent is False

    def test_different_day_sends_again(self) -> None:
        scheduler = Scheduler()
        state = {DataKey.LAST_INTENSITY_PROMPT_DATE.value: "2025-01-01"}
        # This will compare with today's date which is different from 2025-01-01
        sent = scheduler.check_and_send_intensity_adjustment(state, "user1")
        assert sent is True


# ---------------------------------------------------------------------------
# Outbox event dedupe key
# ---------------------------------------------------------------------------


class TestOutboxDedupeKey:
    def test_reminder_dedup_key_format(self) -> None:
        scheduler = Scheduler()
        state = _empty_state()
        now = datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        scheduler.schedule_daily_prompt_reminder(state, "participant_42", sent_at=now)
        event = scheduler.pending_events[0]
        assert event.dedup_key == "daily_prompt_reminder:participant_42"

    def test_auto_feedback_dedup_key_format(self) -> None:
        scheduler = Scheduler()
        state = _empty_state()
        scheduler.schedule_auto_feedback_enforcement(state, "participant_42")
        event = scheduler.pending_events[0]
        assert event.dedup_key == "auto_feedback:participant_42"


# ---------------------------------------------------------------------------
# §5.1 — execute_scheduled_prompt integration
# ---------------------------------------------------------------------------


class TestExecuteScheduledPrompt:
    def test_returns_error_without_profile(self) -> None:
        scheduler = Scheduler()
        state = _empty_state()
        result = scheduler.execute_scheduled_prompt(state, "user1")
        assert result.startswith("error:")

    def test_success_with_complete_profile(self) -> None:
        scheduler = Scheduler()
        state = _state_with_profile(
            prompt_anchor="after coffee", preferred_time="8am"
        )
        result = scheduler.execute_scheduled_prompt(state, "user1")
        assert "error" not in result
        assert state.get(DataKey.LAST_PROMPT_SENT_AT.value, "") != ""
        # Should have outbox events (reminder + auto_feedback)
        assert len(scheduler.pending_events) >= 2
