"""Profile and memory stores: UserProfileStore, MemoryItem, PatchAuditLog, FlowUserProfile."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.core import ProjectMembership


class UserProfileStore(Base):
    """Structured user profile (Store A). Pydantic-validated JSON, single-writer (Router)."""

    __tablename__ = "user_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    membership_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("project_memberships.id"), nullable=False, unique=True
    )
    profile_json: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    membership: Mapped[ProjectMembership] = relationship()


class MemoryItem(Base):
    """Semi-structured memory store (Store B). Conservative writes only."""

    __tablename__ = "memory_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    membership_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("project_memberships.id"), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source_message_ids: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    tags: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    membership: Mapped[ProjectMembership] = relationship()


class PatchAuditLog(Base):
    """Audit trail for all patch proposals and commit decisions."""

    __tablename__ = "patch_audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    membership_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("project_memberships.id"), nullable=False
    )
    proposal_type: Mapped[str] = mapped_column(String(20), nullable=False)
    source_bot: Mapped[str] = mapped_column(String(20), nullable=False)
    patch_json: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    evidence_json: Mapped[str] = mapped_column(Text, nullable=False)
    decision: Mapped[str] = mapped_column(String(255), nullable=False)
    committed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    membership: Mapped[ProjectMembership] = relationship()


class FlowUserProfile(Base):
    """User-level profile extension for display_name (not in upstream User model)."""

    __tablename__ = "flow_user_profiles"

    user_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    email_raw: Mapped[str | None] = mapped_column(String(320), nullable=True)
    email_normalized: Mapped[str | None] = mapped_column(String(320), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tz_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    tz_offset_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
