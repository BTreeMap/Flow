"""State constants, enums, and Pydantic models matching legacy §3."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# §3.1 — Top-level state constant
TOP_LEVEL_STATE = "CONVERSATION_ACTIVE"


class ConversationState(str, Enum):
    """Sub-state stored in DataKeyConversationState (§3.1)."""

    INTAKE = "INTAKE"
    FEEDBACK = "FEEDBACK"


class DataKey(str, Enum):
    """All 18 keys from §3.2."""

    CONVERSATION_HISTORY = "conversationHistory"
    SYSTEM_PROMPT = "systemPrompt"
    PARTICIPANT_BACKGROUND = "participantBackground"
    USER_PROFILE = "userProfile"
    LAST_HABIT_PROMPT = "lastHabitPrompt"
    FEEDBACK_STATE = "feedbackState"
    FEEDBACK_TIMER_ID = "feedbackTimerID"
    FEEDBACK_FOLLOWUP_TIMER_ID = "feedbackFollowupTimerID"
    SCHEDULE_REGISTRY = "scheduleRegistry"
    CONVERSATION_STATE = "conversationState"
    STATE_TRANSITION_TIMER_ID = "stateTransitionTimerID"
    LAST_PROMPT_SENT_AT = "lastPromptSentAt"
    AUTO_FEEDBACK_TIMER_ID = "autoFeedbackTimerID"
    DAILY_PROMPT_PENDING = "dailyPromptPending"
    DAILY_PROMPT_REMINDER_TIMER_ID = "dailyPromptReminderTimerID"
    DAILY_PROMPT_REMINDER_SENT_AT = "dailyPromptReminderSentAt"
    DAILY_PROMPT_RESPONDED_AT = "dailyPromptRespondedAt"
    LAST_INTENSITY_PROMPT_DATE = "lastIntensityPromptDate"


# ---------------------------------------------------------------------------
# Structured data models
# ---------------------------------------------------------------------------


class ProfileTone(BaseModel):
    """Tone data inside UserProfile (§6.3)."""

    tone_tags: list[str] = Field(default_factory=list)
    tone_scores: dict[str, float] = Field(default_factory=dict)
    tone_version: int = 0
    tone_last_updated_at: Optional[datetime] = None
    tone_update_source: Optional[str] = None
    tone_override_until: Optional[datetime] = None


class UserProfile(BaseModel):
    """Structured profile stored as JSON in DataKeyUserProfile (§4.7)."""

    prompt_anchor: str = ""
    preferred_time: str = ""
    habit_domain: str = ""
    motivational_frame: str = ""
    additional_info: str = ""
    last_successful_prompt: str = ""
    last_barrier: str = ""
    last_motivator: str = ""
    last_tweak: str = ""
    intensity: str = "normal"
    total_prompts: int = 0
    success_count: int = 0
    tone: ProfileTone = Field(default_factory=ProfileTone)


class DailyPromptPendingState(BaseModel):
    """Pending daily-prompt state (§5.2)."""

    sent_at: datetime
    to: str = ""
    reminder_due_at: Optional[datetime] = None


class ConversationMessage(BaseModel):
    """A single message in the conversation history (§3.2 #1)."""

    role: str
    content: str
    timestamp: Optional[datetime] = None


class ConversationHistory(BaseModel):
    """Wrapper around the message list (§3.2 #1)."""

    messages: list[ConversationMessage] = Field(default_factory=list)


class ScheduleInfo(BaseModel):
    """One schedule entry in the schedule registry (§3.2 #9)."""

    id: str = ""
    type: str = ""  # "fixed" or "random"
    fixed_time: Optional[str] = None
    random_start_time: Optional[str] = None
    random_end_time: Optional[str] = None
    timezone: str = ""
    created_at: Optional[datetime] = None
    timer_id: str = ""
