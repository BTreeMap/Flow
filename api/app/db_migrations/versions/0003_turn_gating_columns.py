"""Add status, error, updated_at columns to conversation_turns; make user_message_id nullable.

Revision ID: 0003
Revises: 0002
Create Date: 2025-01-03 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add status column with default 'processing'
    op.add_column(
        "conversation_turns",
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="processing",
        ),
    )
    # Add error column
    op.add_column(
        "conversation_turns",
        sa.Column("error", sa.Text, nullable=True),
    )
    # Add updated_at column
    op.add_column(
        "conversation_turns",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # Mark existing turns as completed (they already finished)
    op.execute("UPDATE conversation_turns SET status = 'completed'")

    # Make user_message_id nullable: recreate table for SQLite compatibility
    # For PostgreSQL this would use ALTER COLUMN ... DROP NOT NULL
    # Using batch_alter_table handles both dialects
    with op.batch_alter_table("conversation_turns") as batch_op:
        batch_op.alter_column(
            "user_message_id",
            existing_type=sa.Integer(),
            nullable=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("conversation_turns") as batch_op:
        batch_op.alter_column(
            "user_message_id",
            existing_type=sa.Integer(),
            nullable=False,
        )
    op.drop_column("conversation_turns", "updated_at")
    op.drop_column("conversation_turns", "error")
    op.drop_column("conversation_turns", "status")
