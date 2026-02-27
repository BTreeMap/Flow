"""Pydantic schemas for the new multi-bot architecture: proposals, patches, memory, profiles."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Evidence spans
# ---------------------------------------------------------------------------


class EvidenceSpan(BaseModel):
    """Evidence supporting a patch proposal."""

    message_ids: list[int] = Field(
        ..., description="Internal message ids that support the claim"
    )
    quotes: list[str] = Field(
        default_factory=list, description="Short verbatim snippets from those messages"
    )


# ---------------------------------------------------------------------------
# Profile schema (Store A)
# ---------------------------------------------------------------------------


class UserProfileData(BaseModel):
    """Structured user profile fields (Store A). Pydantic validated."""

    prompt_anchor: str = ""
    preferred_time: str = ""
    habit_domain: str = ""
    motivational_frame: str = ""
    intensity: str = "normal"
    last_successful_prompt: str = ""
    last_barrier: str = ""
    last_motivator: str = ""
    last_tweak: str = ""
    tone_tags: list[str] = Field(default_factory=list)
    tone_scores: dict[str, float] = Field(default_factory=dict)
    total_prompts: int = 0
    success_count: int = 0
    display_name: str | None = None


# ---------------------------------------------------------------------------
# Memory item schema (Store B)
# ---------------------------------------------------------------------------


class MemoryItemData(BaseModel):
    """A single memory item for Store B."""

    content: str = Field(..., description="Short factual statement")
    source_message_ids: list[int] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    created_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Patch proposals
# ---------------------------------------------------------------------------


class ProfilePatchProposal(BaseModel):
    """A specialist bot's proposal to update the user profile."""

    patch: dict = Field(..., description="Partial profile update")
    confidence: float = Field(..., ge=0, le=1)
    evidence: EvidenceSpan
    source_bot: Literal["INTAKE", "FEEDBACK", "COACH"] = Field(
        ..., description="Which bot proposed this"
    )


class MemoryPatchProposal(BaseModel):
    """A specialist bot's proposal to add memory items."""

    items: list[MemoryItemData] = Field(..., description="Memory items to add")
    confidence: float = Field(..., ge=0, le=1)
    evidence: EvidenceSpan
    source_bot: Literal["INTAKE", "FEEDBACK", "COACH"] = Field(
        ..., description="Which bot proposed this"
    )


class SchedulePatchProposal(BaseModel):
    """A specialist bot's proposal to schedule or delete a nudge."""

    action: Literal["create", "delete"]
    topic: str | None = None
    time: str | None = None
    schedule_id: int | None = None
    confidence: float = Field(..., ge=0, le=1)
    evidence: EvidenceSpan
    source_bot: Literal["INTAKE", "FEEDBACK", "COACH"] = Field(
        ..., description="Which bot proposed this"
    )


# ---------------------------------------------------------------------------
# Proposal results
# ---------------------------------------------------------------------------


class PatchProposalResult(BaseModel):
    """Result of a patch proposal tool call."""

    accepted: bool
    reason: str = ""


# ---------------------------------------------------------------------------
# Permission matrix
# ---------------------------------------------------------------------------

# Fields each bot is allowed to propose changes to
INTAKE_ALLOWED_FIELDS: set[str] = {
    "prompt_anchor",
    "preferred_time",
    "habit_domain",
    "motivational_frame",
}

FEEDBACK_ALLOWED_FIELDS: set[str] = {
    "last_barrier",
    "last_tweak",
    "last_successful_prompt",
    "last_motivator",
    "intensity",
    "tone_tags",
    "tone_scores",
}

# Coach can only propose candidates; Router applies conservative thresholds
COACH_ALLOWED_FIELDS: set[str] = set()  # Coach has no direct write permissions

# Confidence thresholds per bot
CONFIDENCE_THRESHOLDS: dict[str, float] = {
    "INTAKE": 0.5,
    "FEEDBACK": 0.5,
    "COACH": 0.8,  # Higher threshold for coach candidates
}
