"""SQLAlchemy 2.x declarative models for the HCI research platform."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
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


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint(
            "conversation_id",
            "client_msg_id",
            name="uq_message_conversation_client_msg",
        ),
    )

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
    participation_id: Mapped[int | None] = mapped_column(
        ForeignKey("participations.id"), nullable=True
    )
    condition_source: Mapped[str] = mapped_column(
        String(20), nullable=False, default="SYSTEM", index=True
    )
    metadata_: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata",
        JSON().with_variant(JSONB, "postgresql"),
        nullable=True,
    )

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


class PushSubscription(Base):
    __tablename__ = "push_subscriptions"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "endpoint", name="uq_push_subscription_user_endpoint"
        ),
        Index("ix_push_sub_user_active", "user_id", "revoked_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(32), nullable=False)
    endpoint: Mapped[str] = mapped_column(String(2048), nullable=False)
    p256dh: Mapped[str] = mapped_column(String(255), nullable=False)
    auth: Mapped[str] = mapped_column(String(255), nullable=False)
    user_agent: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    consecutive_gone_410_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
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
    rule_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("notification_rules.id"), nullable=True
    )
    local_date: Mapped[str | None] = mapped_column(Date, nullable=True)
    dedupe_key: Mapped[str | None] = mapped_column(
        String(255), unique=True, nullable=True
    )

    membership: Mapped[ProjectMembership] = relationship()
    rule: Mapped[NotificationRule | None] = relationship(back_populates="instances")


class NotificationRule(Base):
    """Describes what should happen and when (e.g. daily nudge at 08:00 local)."""

    __tablename__ = "notification_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    membership_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("project_memberships.id"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(50), nullable=False)
    config_json: Mapped[str] = mapped_column(Text, nullable=False)
    tz_policy: Mapped[str] = mapped_column(
        String(30), nullable=False, default="floating_user_tz"
    )
    timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    membership: Mapped[ProjectMembership] = relationship()
    state: Mapped[NotificationRuleState | None] = relationship(
        back_populates="rule", uselist=False
    )
    instances: Mapped[list[Notification]] = relationship(back_populates="rule")


class NotificationRuleState(Base):
    """Hot worker state for a notification rule — indexed for efficient polling."""

    __tablename__ = "notification_rule_state"
    __table_args__ = (Index("ix_rule_state_next_due", "next_due_at_utc"),)

    rule_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("notification_rules.id"), primary_key=True
    )
    next_due_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    locked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    locked_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    rule: Mapped[NotificationRule] = relationship(back_populates="state")


class NotificationDelivery(Base):
    """Short-lived delivery command (push_notify, push_dismiss)."""

    __tablename__ = "notification_deliveries"
    __table_args__ = (
        Index("ix_delivery_run_status", "run_at_utc", "status"),
        Index("ix_delivery_user_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instance_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("notifications.id"), nullable=False
    )
    membership_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("project_memberships.id"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    channel: Mapped[str] = mapped_column(String(30), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    run_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", server_default="pending"
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

    instance: Mapped[Notification] = relationship()
    membership: Mapped[ProjectMembership] = relationship()


class ScheduledTask(Base):
    """Ephemeral task queue for delayed system actions."""

    __tablename__ = "scheduled_tasks"
    __table_args__ = (
        Index("ix_scheduled_task_due", "run_at_utc", "status"),
        Index("ix_scheduled_task_rule", "rule_id"),
        Index("ix_scheduled_task_parent", "parent_instance_id"),
        Index(
            "ix_scheduled_task_membership_type_status",
            "membership_id",
            "task_type",
            "status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    membership_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("project_memberships.id"), nullable=False
    )
    rule_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("notification_rules.id", ondelete="CASCADE"), nullable=True
    )
    # Parent nudge notification id for delayed feedback tasks; null for standalone tasks.
    parent_instance_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("notifications.id", ondelete="CASCADE"), nullable=True
    )
    task_type: Mapped[str] = mapped_column(String(50), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    run_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", server_default="pending"
    )
    locked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    locked_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    membership: Mapped[ProjectMembership] = relationship()
