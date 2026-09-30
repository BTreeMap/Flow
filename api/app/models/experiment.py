"""Experiment models: participations, daily intervention logs, daily summaries."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Participation(Base):
    __tablename__ = "participations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    membership_id: Mapped[int] = mapped_column(
        ForeignKey("project_memberships.id"), nullable=False
    )
    study_id: Mapped[str] = mapped_column(String(50), nullable=False)
    study_start_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    timezone: Mapped[str] = mapped_column(String(50), nullable=False, default="UTC")


class DailyInterventionLog(Base):
    __tablename__ = "daily_intervention_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    participation_id: Mapped[int] = mapped_column(
        ForeignKey("participations.id"), nullable=False
    )
    intervention_date: Mapped[date] = mapped_column(Date, nullable=False)
    study_day_index: Mapped[int] = mapped_column(Integer, nullable=False)
    assigned_condition: Mapped[str] = mapped_column(String(1), nullable=False)
    extracted_state: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=True,
    )


class DailySummary(Base):
    """End-of-day clinical summary acting as the cross-condition semantic firewall.

    One short, sterilized row per ``(participation_id, summary_date)``. The
    summary is produced by the EOD Memory Condensation Agent (see
    ``app/services/eod_summarizer.py``) and is read by both Condition C
    and Condition D so the LLM retains multi-day memory without ever
    seeing the raw framing produced under the other condition.

    This table has its own writer (the summarizer) — it is NOT subject to
    the Router single-writer rule that governs ``UserProfileStore`` and
    ``MemoryItem``.
    """

    __tablename__ = "daily_summaries"
    __table_args__ = (
        UniqueConstraint(
            "participation_id",
            "summary_date",
            name="uq_daily_summary_participation_date",
        ),
        Index(
            "ix_daily_summary_participation_date", "participation_id", "summary_date"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    participation_id: Mapped[int] = mapped_column(
        ForeignKey("participations.id"), nullable=False
    )
    summary_date: Mapped[date] = mapped_column(Date, nullable=False)
    summary_text: Mapped[str] = mapped_column(Text, nullable=False)
    previous_summary_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    message_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    # One of: "clean" (passed regex first try), "regenerated" (passed after
    # one or more retries), "fallback" (regex still failed; deterministic
    # skeleton written instead of LLM output).
    sterilization_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="clean", server_default="clean"
    )
    prompt_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
