"""Add experimental participation tables and message condition fields.

Revision ID: 0011
Revises: 0010
Create Date: 2026-05-11 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "participations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "membership_id",
            sa.Integer(),
            sa.ForeignKey("project_memberships.id"),
            nullable=False,
        ),
        sa.Column("study_id", sa.String(length=50), nullable=False),
        sa.Column("study_start_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "timezone", sa.String(length=50), nullable=False, server_default="UTC"
        ),
    )

    with op.batch_alter_table("messages") as batch:
        batch.add_column(sa.Column("participation_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_messages_participation_id_participations",
            "participations",
            ["participation_id"],
            ["id"],
        )
        batch.add_column(
            sa.Column(
                "condition_source",
                sa.String(length=20),
                nullable=False,
                server_default="SYSTEM",
            )
        )
        batch.create_index("ix_messages_condition_source", ["condition_source"])

    op.create_table(
        "daily_intervention_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "participation_id",
            sa.Integer(),
            sa.ForeignKey("participations.id"),
            nullable=False,
        ),
        sa.Column("intervention_date", sa.Date(), nullable=False),
        sa.Column("study_day_index", sa.Integer(), nullable=False),
        sa.Column("assigned_condition", sa.String(length=1), nullable=False),
        sa.Column("extracted_state", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("daily_intervention_logs")

    with op.batch_alter_table("messages") as batch:
        batch.drop_constraint(
            "fk_messages_participation_id_participations",
            type_="foreignkey",
        )
        batch.drop_index("ix_messages_condition_source")
        batch.drop_column("condition_source")
        batch.drop_column("participation_id")

    op.drop_table("participations")
