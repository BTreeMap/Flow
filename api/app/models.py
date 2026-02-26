"""SQLAlchemy 2.x declarative models for the HCI research platform."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Shared declarative base for all models."""


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
    outbox_events: Mapped[list[OutboxEvent]] = relationship(back_populates="project")


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
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
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
    push_subscriptions: Mapped[list[PushSubscription]] = relationship(
        back_populates="membership"
    )
    outbox_events: Mapped[list[OutboxEvent]] = relationship(back_populates="membership")


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


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("conversations.id"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    client_msg_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    server_msg_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class ConversationRuntimeState(Base):
    __tablename__ = "conversation_runtime_state"

    conversation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("conversations.id"), primary_key=True
    )
    state_json: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    conversation: Mapped[Conversation] = relationship(back_populates="runtime_state")


class PushSubscription(Base):
    __tablename__ = "push_subscriptions"
    __table_args__ = (
        UniqueConstraint(
            "membership_id", "endpoint", name="uq_push_subscription_membership_endpoint"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    membership_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("project_memberships.id"), nullable=False
    )
    endpoint: Mapped[str] = mapped_column(String(2048), nullable=False)
    p256dh: Mapped[str] = mapped_column(String(255), nullable=False)
    auth: Mapped[str] = mapped_column(String(255), nullable=False)
    user_agent: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_success_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_failure_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    membership: Mapped[ProjectMembership] = relationship(
        back_populates="push_subscriptions"
    )


class OutboxEvent(Base):
    __tablename__ = "outbox_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("projects.id"), nullable=False
    )
    membership_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("project_memberships.id"), nullable=False
    )
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    dedupe_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    locked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    locked_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    project: Mapped[Project] = relationship(back_populates="outbox_events")
    membership: Mapped[ProjectMembership] = relationship(back_populates="outbox_events")


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
    decision: Mapped[str] = mapped_column(String(30), nullable=False)
    committed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    membership: Mapped[ProjectMembership] = relationship()


class ConversationEvent(Base):
    """Persisted SSE event for durable replay via Last-Event-ID."""

    __tablename__ = "conversation_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("conversations.id"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ConversationTurn(Base):
    """Deduplicate user messages via client_msg_id with turn gating."""

    __tablename__ = "conversation_turns"
    __table_args__ = (
        UniqueConstraint(
            "conversation_id",
            "client_msg_id",
            name="uq_turn_conversation_client_msg",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("conversations.id"), nullable=False
    )
    client_msg_id: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="processing", server_default="processing"
    )
    user_message_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("messages.id"), nullable=True
    )
    assistant_message_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("messages.id"), nullable=True
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class FlowUserProfile(Base):
    """User-level profile extension for display_name (not in upstream User model)."""

    __tablename__ = "flow_user_profiles"

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    email_raw: Mapped[str | None] = mapped_column(String(320), nullable=True)
    email_normalized: Mapped[str | None] = mapped_column(String(320), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class NudgeSchedule(Base):
    __tablename__ = "nudge_schedules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    membership_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("project_memberships.id"), nullable=False
    )
    topic: Mapped[str] = mapped_column(String(255), nullable=False)
    cron_rule: Mapped[str] = mapped_column(String(50), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    membership: Mapped[ProjectMembership] = relationship()


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    membership_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("project_memberships.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    membership: Mapped[ProjectMembership] = relationship()
