"""Notification and scheduling models."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.core import ProjectMembership


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
