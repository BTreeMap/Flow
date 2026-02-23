"""Initial Flow schema.

Revision ID: 0001
Revises: None
Create Date: 2025-01-01 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("study_settings_json", sa.Text, nullable=True),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="active",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "project_invites",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "project_id",
            sa.String(32),
            sa.ForeignKey("projects.id"),
            nullable=False,
        ),
        sa.Column("invite_code_hash", sa.String(255), nullable=False),
        sa.Column("label", sa.String(255), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("max_uses", sa.Integer, nullable=True),
        sa.Column("uses", sa.Integer, nullable=False, server_default="0"),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "project_memberships",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "project_id",
            sa.String(32),
            sa.ForeignKey("projects.id"),
            nullable=False,
        ),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("project_id", "user_id", name="uq_membership_project_user"),
    )

    op.create_table(
        "participant_contacts",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "membership_id",
            sa.Integer,
            sa.ForeignKey("project_memberships.id"),
            nullable=False,
        ),
        sa.Column("email_raw", sa.String(320), nullable=False),
        sa.Column("email_normalized", sa.String(320), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "conversations",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "membership_id",
            sa.Integer,
            sa.ForeignKey("project_memberships.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("membership_id", name="uq_conversation_membership"),
    )

    op.create_table(
        "messages",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "conversation_id",
            sa.Integer,
            sa.ForeignKey("conversations.id"),
            nullable=False,
        ),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("client_msg_id", sa.String(255), nullable=True),
        sa.Column("server_msg_id", sa.String(36), unique=True, nullable=False),
    )

    op.create_table(
        "conversation_runtime_state",
        sa.Column(
            "conversation_id",
            sa.Integer,
            sa.ForeignKey("conversations.id"),
            primary_key=True,
        ),
        sa.Column("state_json", sa.Text, nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "push_subscriptions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "membership_id",
            sa.Integer,
            sa.ForeignKey("project_memberships.id"),
            nullable=False,
        ),
        sa.Column("endpoint", sa.String(2048), nullable=False),
        sa.Column("p256dh", sa.String(255), nullable=False),
        sa.Column("auth", sa.String(255), nullable=False),
        sa.Column("user_agent", sa.String(512), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_failure_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "membership_id",
            "endpoint",
            name="uq_push_subscription_membership_endpoint",
        ),
    )

    op.create_table(
        "outbox_events",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "project_id",
            sa.String(32),
            sa.ForeignKey("projects.id"),
            nullable=False,
        ),
        sa.Column(
            "membership_id",
            sa.Integer,
            sa.ForeignKey("project_memberships.id"),
            nullable=False,
        ),
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column("payload_json", sa.Text, nullable=False),
        sa.Column("dedupe_key", sa.String(255), unique=True, nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_by", sa.String(128), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "user_profiles",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "membership_id",
            sa.Integer,
            sa.ForeignKey("project_memberships.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("profile_json", sa.Text, nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "memory_items",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "membership_id",
            sa.Integer,
            sa.ForeignKey("project_memberships.id"),
            nullable=False,
        ),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("source_message_ids", sa.Text, nullable=False, server_default="[]"),
        sa.Column("tags", sa.String(512), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "patch_audit_log",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "membership_id",
            sa.Integer,
            sa.ForeignKey("project_memberships.id"),
            nullable=False,
        ),
        sa.Column("proposal_type", sa.String(20), nullable=False),
        sa.Column("source_bot", sa.String(20), nullable=False),
        sa.Column("patch_json", sa.Text, nullable=False),
        sa.Column("confidence", sa.Float, nullable=False),
        sa.Column("evidence_json", sa.Text, nullable=False),
        sa.Column("decision", sa.String(30), nullable=False),
        sa.Column("committed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "flow_user_profiles",
        sa.Column("user_id", sa.String(64), primary_key=True),
        sa.Column("email_raw", sa.String(320), nullable=True),
        sa.Column("email_normalized", sa.String(320), nullable=True),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("flow_user_profiles")
    op.drop_table("patch_audit_log")
    op.drop_table("memory_items")
    op.drop_table("user_profiles")
    op.drop_table("outbox_events")
    op.drop_table("push_subscriptions")
    op.drop_table("conversation_runtime_state")
    op.drop_table("messages")
    op.drop_table("conversations")
    op.drop_table("participant_contacts")
    op.drop_table("project_memberships")
    op.drop_table("project_invites")
    op.drop_table("projects")
