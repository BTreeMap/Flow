"""Delete legacy scheduled_prompt outbox events.

Revision ID: 0005
Revises: 0004
Create Date: 2025-06-01 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(sa.text("DELETE FROM outbox_events WHERE type = 'scheduled_prompt'"))


def downgrade() -> None:
    # Data deletion is not reversible
    pass
