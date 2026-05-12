"""Pydantic schemas for LangChain tool arguments and results."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# ProfileSaveTool (§4.7)
# ---------------------------------------------------------------------------


class ProfileSaveArgs(BaseModel):
    """Arguments for the save_user_profile tool."""

    prompt_anchor: str = Field(default="", description="Habit anchor cue")
    preferred_time: str = Field(default="", description="Preferred time for prompts")
    habit_domain: str = Field(default="", description="Habit domain category")
    motivational_frame: str = Field(default="", description="Motivational framing")
    additional_info: str = Field(default="", description="Free-form additional info")
    last_successful_prompt: str = Field(
        default="", description="Last prompt that worked"
    )
    last_barrier: str = Field(default="", description="Last barrier encountered")
    last_motivator: str = Field(default="", description="Last motivator noted")
    last_tweak: str = Field(default="", description="Last adjustment made")
    tone_tags: list[str] | None = Field(default=None, description="Proposed tone tags")
    tone_update_source: str = Field(
        default="implicit", description="Source: 'explicit' or 'implicit'"
    )
    tone_confidence: float = Field(default=1.0, description="Confidence 0-1")


class ProfileSaveResult(BaseModel):
    """Result from the save_user_profile tool."""

    ok: bool
    status: str = Field(description="'success' or 'noop'")
    error: str | None = None


# ---------------------------------------------------------------------------
# SchedulerTool (§4.4)
# ---------------------------------------------------------------------------


class SchedulerArgs(BaseModel):
    """Arguments for the scheduler tool."""

    action: Literal["create", "list", "delete"] = Field(
        ..., description="Scheduler action"
    )
    type: str | None = Field(
        default=None, description="Schedule type: 'fixed' or 'random'"
    )
    fixed_time: str | None = Field(default=None, description="Fixed time (HH:MM)")
    timezone: str | None = Field(default=None, description="IANA timezone")
    random_start_time: str | None = Field(
        default=None, description="Random window start"
    )
    random_end_time: str | None = Field(default=None, description="Random window end")
    rule_id: str | None = Field(
        default=None, description="Notification rule ID for delete"
    )


class SchedulerResult(BaseModel):
    """Result from the scheduler tool."""

    ok: bool
    message: str
    error: str | None = None


# ---------------------------------------------------------------------------
# GenerateHabitPromptTool (§4.5)
# ---------------------------------------------------------------------------


class GenerateHabitPromptArgs(BaseModel):
    """Arguments for the generate_habit_prompt tool."""

    delivery_mode: str = Field(
        default="immediate",
        description="Delivery mode: 'immediate' or 'scheduled'",
    )
    personalization_notes: str = Field(
        default="", description="Extra personalization notes"
    )


class GenerateHabitPromptResult(BaseModel):
    """Result from the generate_habit_prompt tool."""

    ok: bool
    prompt: str | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# StateTransitionTool (§4.6)
# ---------------------------------------------------------------------------


class StateTransitionArgs(BaseModel):
    """Arguments for the transition_state tool."""

    target_state: Literal["INTAKE", "FEEDBACK"] = Field(
        ..., description="Target conversation state"
    )
    delay_minutes: float = Field(
        default=0, description="Delay in minutes (0 = immediate)"
    )
    reason: str = Field(default="", description="Reason for transition")


class StateTransitionResult(BaseModel):
    """Result from the transition_state tool."""

    ok: bool
    applied_state: str | None = None
    scheduled_for: str | None = None
    error: str | None = None
