"""Add pseudonymous Spark research identity and interaction telemetry.

Revision ID: 0013
Revises: 0012
Create Date: 2026-07-14 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "spark_participants",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("installation_key_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "installation_key_hash", name="uq_spark_participants_installation_key_hash"
        ),
    )
    op.create_index(
        "ix_spark_participants_last_seen_at",
        "spark_participants",
        ["last_seen_at"],
    )

    op.create_table(
        "spark_fingerprint_observations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "participant_id",
            sa.Integer(),
            sa.ForeignKey("spark_participants.id"),
            nullable=False,
        ),
        sa.Column("fingerprint_hash", sa.String(length=64), nullable=False),
        sa.Column("fingerprint_version", sa.String(length=64), nullable=True),
        sa.Column("last_timezone", sa.String(length=64), nullable=True),
        sa.Column("last_locale", sa.String(length=35), nullable=True),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "observation_count",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
        sa.UniqueConstraint(
            "participant_id",
            "fingerprint_hash",
            name="uq_spark_fingerprint_observation",
        ),
    )
    op.create_index(
        "ix_spark_fingerprint_observations_fingerprint_hash",
        "spark_fingerprint_observations",
        ["fingerprint_hash"],
    )
    op.create_index(
        "ix_spark_fingerprint_observations_participant_id",
        "spark_fingerprint_observations",
        ["participant_id"],
    )

    op.create_table(
        "spark_interactions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "participant_id",
            sa.Integer(),
            sa.ForeignKey("spark_participants.id"),
            nullable=False,
        ),
        sa.Column("flow_id", sa.String(length=36), nullable=False),
        sa.Column("client_event_id", sa.String(length=36), nullable=False),
        sa.Column("condition", sa.String(length=1), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column(
            "payload_json",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "participant_id",
            "client_event_id",
            name="uq_spark_interactions_participant_event",
        ),
    )
    op.create_index(
        "ix_spark_interactions_participant_condition_created",
        "spark_interactions",
        ["participant_id", "condition", "created_at"],
    )
    op.create_index("ix_spark_interactions_flow_id", "spark_interactions", ["flow_id"])


def downgrade() -> None:
    op.drop_index("ix_spark_interactions_flow_id", table_name="spark_interactions")
    op.drop_index(
        "ix_spark_interactions_participant_condition_created",
        table_name="spark_interactions",
    )
    op.drop_table("spark_interactions")

    op.drop_index(
        "ix_spark_fingerprint_observations_participant_id",
        table_name="spark_fingerprint_observations",
    )
    op.drop_index(
        "ix_spark_fingerprint_observations_fingerprint_hash",
        table_name="spark_fingerprint_observations",
    )
    op.drop_table("spark_fingerprint_observations")

    op.drop_index("ix_spark_participants_last_seen_at", table_name="spark_participants")
    op.drop_table("spark_participants")
