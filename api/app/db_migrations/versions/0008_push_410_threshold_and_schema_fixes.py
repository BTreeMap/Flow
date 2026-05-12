"""Add consecutive_gone_410_count, widen decision column, shrink user_id to 32.

Revision ID: 0008
Revises: 0007
Create Date: 2026-03-05 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- 1. Add consecutive_gone_410_count to push_subscriptions ---
    with op.batch_alter_table("push_subscriptions") as batch:
        batch.add_column(
            sa.Column(
                "consecutive_gone_410_count",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )

    # --- 2. Widen patch_audit_log.decision from String(30) to String(255) ---
    with op.batch_alter_table("patch_audit_log") as batch:
        batch.alter_column(
            "decision",
            existing_type=sa.String(30),
            type_=sa.String(255),
            existing_nullable=False,
        )

    # --- 3. Shrink user_id columns from String(64) to String(32) ---
    with op.batch_alter_table("project_memberships") as batch:
        batch.alter_column(
            "user_id",
            existing_type=sa.String(64),
            type_=sa.String(32),
            existing_nullable=False,
        )

    with op.batch_alter_table("push_subscriptions") as batch:
        batch.alter_column(
            "user_id",
            existing_type=sa.String(64),
            type_=sa.String(32),
            existing_nullable=False,
        )

    with op.batch_alter_table("flow_user_profiles") as batch:
        batch.alter_column(
            "user_id",
            existing_type=sa.String(64),
            type_=sa.String(32),
            existing_nullable=False,
        )

    with op.batch_alter_table("notification_deliveries") as batch:
        batch.alter_column(
            "user_id",
            existing_type=sa.String(64),
            type_=sa.String(32),
            existing_nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("notification_deliveries") as batch:
        batch.alter_column(
            "user_id",
            existing_type=sa.String(32),
            type_=sa.String(64),
            existing_nullable=False,
        )

    with op.batch_alter_table("flow_user_profiles") as batch:
        batch.alter_column(
            "user_id",
            existing_type=sa.String(32),
            type_=sa.String(64),
            existing_nullable=False,
        )

    with op.batch_alter_table("push_subscriptions") as batch:
        batch.alter_column(
            "user_id",
            existing_type=sa.String(32),
            type_=sa.String(64),
            existing_nullable=False,
        )

    with op.batch_alter_table("project_memberships") as batch:
        batch.alter_column(
            "user_id",
            existing_type=sa.String(32),
            type_=sa.String(64),
            existing_nullable=False,
        )

    with op.batch_alter_table("patch_audit_log") as batch:
        batch.alter_column(
            "decision",
            existing_type=sa.String(255),
            type_=sa.String(30),
            existing_nullable=False,
        )

    with op.batch_alter_table("push_subscriptions") as batch:
        batch.drop_column("consecutive_gone_410_count")
