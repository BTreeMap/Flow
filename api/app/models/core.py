"""Core project, membership, contact, and conversation models."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.messaging import ConversationRuntimeState, Message


# ---- User-visible, custom id ------------------------------------------------


class Project(Base):
    """User-visible project entity. ID uses custom scheme: 'p' + 31 base32 chars (32 total)."""

    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    study_settings_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active", server_default="active"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    invites: Mapped[list[ProjectInvite]] = relationship(back_populates="project")
    memberships: Mapped[list[ProjectMembership]] = relationship(
        back_populates="project"
    )


# ---- Internal entities -------------------------------------------------------


class ProjectInvite(Base):
    __tablename__ = "project_invites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("projects.id"), nullable=False
    )
    invite_code_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    max_uses: Mapped[int | None] = mapped_column(Integer, nullable=True)
    uses: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    project: Mapped[Project] = relationship(back_populates="invites")


class ProjectMembership(Base):
    __tablename__ = "project_memberships"
    __table_args__ = (
        UniqueConstraint("project_id", "user_id", name="uq_membership_project_user"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("projects.id"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    project: Mapped[Project] = relationship(back_populates="memberships")
    contacts: Mapped[list[ParticipantContact]] = relationship(
        back_populates="membership"
    )
    conversations: Mapped[list[Conversation]] = relationship(
        back_populates="membership"
    )


class ParticipantContact(Base):
    __tablename__ = "participant_contacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    membership_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("project_memberships.id"), nullable=False
    )
    email_raw: Mapped[str] = mapped_column(String(320), nullable=False)
    email_normalized: Mapped[str | None] = mapped_column(String(320), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    membership: Mapped[ProjectMembership] = relationship(back_populates="contacts")


class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = (
        UniqueConstraint("membership_id", name="uq_conversation_membership"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    membership_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("project_memberships.id"), nullable=False, unique=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    membership: Mapped[ProjectMembership] = relationship(back_populates="conversations")
    messages: Mapped[list[Message]] = relationship(back_populates="conversation")
    runtime_state: Mapped[ConversationRuntimeState | None] = relationship(
        back_populates="conversation", uselist=False
    )
