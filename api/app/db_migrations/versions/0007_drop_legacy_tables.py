"""Drop legacy tables, make push_subscriptions user-scoped, add user_id to deliveries.

Revision ID: 0007
Revises: 0006
Create Date: 2026-03-04 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- 1. Drop legacy tables ---
    op.drop_table("nudge_schedules")
    op.drop_table("outbox_events")

    # --- 2. Recreate push_subscriptions as user-scoped ---
    # Drop old table and recreate with new schema
    op.drop_table("push_subscriptions")
    op.create_table(
        "push_subscriptions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("endpoint", sa.String(2048), nullable=False),
        sa.Column("p256dh", sa.String(255), nullable=False),
        sa.Column("auth", sa.String(255), nullable=False),
        sa.Column("user_agent", sa.String(512), nullable=False, server_default=""),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_failure_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "endpoint", name="uq_push_subscription_user_endpoint"
        ),
    )
    op.create_index(
        "ix_push_sub_user_active", "push_subscriptions", ["user_id", "revoked_at"]
    )

    # --- 3. Add user_id to notification_deliveries ---
    with op.batch_alter_table("notification_deliveries") as batch:
        batch.add_column(
            sa.Column("user_id", sa.String(64), nullable=False, server_default="")
        )
    op.create_index("ix_delivery_user_id", "notification_deliveries", ["user_id"])


def downgrade() -> None:
    raise RuntimeError(
        "Downgrade of 0007 is destructive: push_subscriptions was recreated "
        "with a new schema and legacy tables (outbox_events, nudge_schedules) "
        "were dropped. Restore from backup if you need to revert."
    )
