"""Strict request models for the anonymous Spark research telemetry plane.

The browser sends a persistent, random installation identifier from localStorage
and an optional ThumbmarkJS fingerprint. Route handlers immediately derive
BLAKE3 keyed hashes and never persist or log either raw identifier.
"""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.services.spark_duration import (
    MAX_DURATION_SECONDS,
    MIN_DURATION_SECONDS,
    DurationSource,
)
from app.services.spark_library import SparkFrame


class SparkClientIdentity(BaseModel):
    """Pseudonymous identity inputs supplied on every Spark request."""

    model_config = ConfigDict(extra="forbid")

    installation_id: UUID
    fingerprint: str | None = Field(default=None, min_length=1, max_length=512)
    fingerprint_version: str | None = Field(default=None, max_length=64)
    timezone: str | None = Field(default=None, max_length=64)
    locale: str | None = Field(default=None, max_length=35)


class SparkFlowStartedEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: Literal["flow_started"]


class SparkIntakeAnsweredEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: Literal["intake_answered"]
    # No "frame": the intake never asks participants to name a vibe up front.
    # A chosen vibe is reported by SparkFrameSelectedEvent once they have seen
    # actual Sparks, so the two events can no longer disagree.
    #
    # No "time" either. That question asked when to send a reminder, nothing in
    # Spark schedules one, and its only consumer fed "time: Morning" into a card
    # the participant does immediately. Rows already carrying field="time" stay
    # readable -- payloads are stored as JSON and this bound is on new requests.
    field: Literal["anchor", "action"]
    value: str = Field(min_length=1, max_length=120)


class SparkFrameSelectedEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: Literal["frame_selected"]
    frame: SparkFrame


class SparkCardSelectedEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: Literal["card_selected"]
    # 1-based position in the flat list the participant chose from: condition B's
    # one-per-vibe sampler, or condition D's ranked catalog. Both offer at most
    # one Spark per vibe, so the list is never longer than five. Pair it with the
    # frame_selected event emitted at the same moment to locate the card exactly.
    rank: int = Field(ge=1, le=5)


class SparkTimerFinishedEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: Literal["timer_finished"]
    completion: Literal["completed", "skipped"]
    # The countdown is participant-configurable, so `completion` alone is not
    # comparable across participants: "completed" at 30s and at 300s are
    # different events. All three fields are required together -- duration
    # without its source cannot be told apart from a changed study default, and
    # elapsed without duration cannot be normalized.
    duration_seconds: int = Field(
        ge=MIN_DURATION_SECONDS,
        le=MAX_DURATION_SECONDS,
    )
    # Measured from a monotonic clock, not by counting ticks, so a throttled
    # background tab cannot under-report it. Bounded well above the maximum
    # duration to absorb the time a participant spends before skipping.
    elapsed_ms: int = Field(ge=0, le=3_600_000)
    duration_source: DurationSource


class SparkFeedbackSubmittedEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: Literal["feedback_submitted"]
    tried: int = Field(ge=0, le=2)
    reason: str | None = Field(default=None, max_length=100)
    tweak: str = Field(default="", max_length=400)


class SparkCueSelectedEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: Literal["cue_selected"]
    cue: str = Field(min_length=1, max_length=120)
    # No "reminder". Spark offered "add to calendar" and "email me" and did
    # neither: there is no calendar export, no mail path, and -- Spark being
    # account-free by design -- no address to mail. The cue is the stated
    # intention; it was never a delivery instruction.
    confidence: int | None = Field(default=None, ge=1, le=5)


class SparkConditionCompletedEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: Literal["condition_completed"]
    fit: int = Field(ge=1, le=5)
    clarity: int = Field(ge=1, le=5)
    willing: int = Field(ge=1, le=5)


SparkClientEvent = Annotated[
    SparkFlowStartedEvent
    | SparkIntakeAnsweredEvent
    | SparkFrameSelectedEvent
    | SparkCardSelectedEvent
    | SparkTimerFinishedEvent
    | SparkFeedbackSubmittedEvent
    | SparkCueSelectedEvent
    | SparkConditionCompletedEvent,
    Field(discriminator="event_type"),
]


class SparkEventRequest(BaseModel):
    """An idempotent, immutable client-side Spark interaction event."""

    model_config = ConfigDict(extra="forbid")

    identity: SparkClientIdentity
    flow_id: UUID
    client_event_id: UUID
    condition: Literal["A", "B", "C", "D"]
    event: SparkClientEvent
