"""Add daily_summaries table for the EOD memory condensation agent.

Revision ID: 0012
Revises: 0011
Create Date: 2026-05-21 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "daily_summaries",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "participation_id",
            sa.Integer(),
            sa.ForeignKey("participations.id"),
            nullable=False,
        ),
        sa.Column("summary_date", sa.Date(), nullable=False),
        sa.Column("summary_text", sa.Text(), nullable=False),
        sa.Column("previous_summary_text", sa.Text(), nullable=True),
        sa.Column(
            "message_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "sterilization_status",
            sa.String(length=16),
            nullable=False,
            server_default="clean",
        ),
        sa.Column("prompt_sha256", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "participation_id",
            "summary_date",
            name="uq_daily_summary_participation_date",
        ),
    )
    op.create_index(
        "ix_daily_summary_participation_date",
        "daily_summaries",
        ["participation_id", "summary_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_daily_summary_participation_date", table_name="daily_summaries")
    op.drop_table("daily_summaries")
