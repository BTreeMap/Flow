"""Persistent, pseudonymous research records for the independent Spark prototype."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class SparkParticipant(Base):
    """Anonymous participant anchored by a hashed browser-local installation id.

    ``installation_key_hash`` is a BLAKE3 keyed digest. The raw localStorage
    identifier is never stored, logged, or exposed through an API.
    """

    __tablename__ = "spark_participants"
    __table_args__ = (Index("ix_spark_participants_last_seen_at", "last_seen_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    installation_key_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True
    )
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SparkFingerprintObservation(Base):
    """A non-reversible fingerprint observation associated with a participant.

    A fingerprint is deliberately an observation, not the primary key. This
    preserves an installation's longitudinal identity when browser signals
    change and makes collisions or instability measurable for researchers.
    """

    __tablename__ = "spark_fingerprint_observations"
    __table_args__ = (
        UniqueConstraint(
            "participant_id",
            "fingerprint_hash",
            name="uq_spark_fingerprint_observation",
        ),
        Index(
            "ix_spark_fingerprint_observations_fingerprint_hash",
            "fingerprint_hash",
        ),
        Index(
            "ix_spark_fingerprint_observations_participant_id",
            "participant_id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    participant_id: Mapped[int] = mapped_column(
        ForeignKey("spark_participants.id"), nullable=False
    )
    fingerprint_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    fingerprint_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_locale: Mapped[str | None] = mapped_column(String(35), nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    observation_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )


class SparkInteraction(Base):
    """Immutable research event for an anonymous Spark participant."""

    __tablename__ = "spark_interactions"
    __table_args__ = (
        UniqueConstraint(
            "participant_id",
            "client_event_id",
            name="uq_spark_interactions_participant_event",
        ),
        Index(
            "ix_spark_interactions_participant_condition_created",
            "participant_id",
            "condition",
            "created_at",
        ),
        Index("ix_spark_interactions_flow_id", "flow_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    participant_id: Mapped[int] = mapped_column(
        ForeignKey("spark_participants.id"), nullable=False
    )
    flow_id: Mapped[str] = mapped_column(String(36), nullable=False)
    client_event_id: Mapped[str] = mapped_column(String(36), nullable=False)
    condition: Mapped[str] = mapped_column(String(1), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
