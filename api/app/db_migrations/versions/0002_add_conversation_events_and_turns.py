"""Add conversation_events and conversation_turns tables.

Revision ID: 0002
Revises: 0001
Create Date: 2025-01-02 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "conversation_events",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "conversation_id",
            sa.Integer,
            sa.ForeignKey("conversations.id"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("payload_json", sa.Text, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_conversation_events_conversation_id",
        "conversation_events",
        ["conversation_id"],
    )

    op.create_table(
        "conversation_turns",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "conversation_id",
            sa.Integer,
            sa.ForeignKey("conversations.id"),
            nullable=False,
        ),
        sa.Column("client_msg_id", sa.String(255), nullable=False),
        sa.Column(
            "user_message_id",
            sa.Integer,
            sa.ForeignKey("messages.id"),
            nullable=False,
        ),
        sa.Column(
            "assistant_message_id",
            sa.Integer,
            sa.ForeignKey("messages.id"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "conversation_id",
            "client_msg_id",
            name="uq_turn_conversation_client_msg",
        ),
    )


def downgrade() -> None:
    op.drop_table("conversation_turns")
    op.drop_index(
        "ix_conversation_events_conversation_id", table_name="conversation_events"
    )
    op.drop_table("conversation_events")
