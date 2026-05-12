"""Add scheduled_tasks table for delayed automated feedback loop.

Revision ID: 0009
Revises: 0008
Create Date: 2026-03-25 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "scheduled_tasks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("membership_id", sa.Integer(), nullable=False),
        sa.Column("rule_id", sa.Integer(), nullable=True),
        sa.Column("parent_instance_id", sa.Integer(), nullable=True),
        sa.Column("task_type", sa.String(length=50), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("run_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="pending"
        ),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_by", sa.String(length=128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["membership_id"], ["project_memberships.id"]),
        sa.ForeignKeyConstraint(
            ["rule_id"],
            ["notification_rules.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["parent_instance_id"],
            ["notifications.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_scheduled_task_due",
        "scheduled_tasks",
        ["run_at_utc", "status"],
    )
    op.create_index("ix_scheduled_task_rule", "scheduled_tasks", ["rule_id"])
    op.create_index(
        "ix_scheduled_task_parent", "scheduled_tasks", ["parent_instance_id"]
    )
    op.create_index(
        "ix_scheduled_task_membership_type_status",
        "scheduled_tasks",
        ["membership_id", "task_type", "status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_scheduled_task_membership_type_status", table_name="scheduled_tasks"
    )
    op.drop_index("ix_scheduled_task_parent", table_name="scheduled_tasks")
    op.drop_index("ix_scheduled_task_rule", table_name="scheduled_tasks")
    op.drop_index("ix_scheduled_task_due", table_name="scheduled_tasks")
    op.drop_table("scheduled_tasks")
