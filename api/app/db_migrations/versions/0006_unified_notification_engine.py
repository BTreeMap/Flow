"""Unified notification engine: rules, instances, deliveries, timezone support.

Revision ID: 0006
Revises: 0005
Create Date: 2026-03-04 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _is_sqlite() -> bool:
    return op.get_bind().dialect.name == "sqlite"


def upgrade() -> None:
    # --- 1. FlowUserProfile: add timezone columns ---
    with op.batch_alter_table("flow_user_profiles") as batch:
        batch.add_column(sa.Column("timezone", sa.String(64), nullable=True))
        batch.add_column(
            sa.Column("tz_updated_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch.add_column(sa.Column("tz_offset_minutes", sa.Integer(), nullable=True))

    # --- 2. notification_rules ---
    op.create_table(
        "notification_rules",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("membership_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(50), nullable=False),
        sa.Column("config_json", sa.Text(), nullable=False),
        sa.Column(
            "tz_policy",
            sa.String(30),
            nullable=False,
            server_default="floating_user_tz",
        ),
        sa.Column("timezone", sa.String(64), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="1", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["membership_id"], ["project_memberships.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # --- 3. notification_rule_state ---
    op.create_table(
        "notification_rule_state",
        sa.Column("rule_id", sa.Integer(), nullable=False),
        sa.Column("next_due_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_by", sa.String(128), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["rule_id"], ["notification_rules.id"]),
        sa.PrimaryKeyConstraint("rule_id"),
    )
    op.create_index(
        "ix_rule_state_next_due",
        "notification_rule_state",
        ["next_due_at_utc"],
    )

    # --- 4. notification_deliveries ---
    op.create_table(
        "notification_deliveries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("instance_id", sa.Integer(), nullable=False),
        sa.Column("membership_id", sa.Integer(), nullable=False),
        sa.Column("channel", sa.String(30), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("run_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            sa.String(20),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_by", sa.String(128), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["instance_id"], ["notifications.id"]),
        sa.ForeignKeyConstraint(["membership_id"], ["project_memberships.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_delivery_run_status",
        "notification_deliveries",
        ["run_at_utc", "status"],
    )

    # --- 5. notifications: add rule_id, local_date, dedupe_key ---
    with op.batch_alter_table("notifications") as batch:
        batch.add_column(sa.Column("rule_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("local_date", sa.Date(), nullable=True))
        batch.add_column(sa.Column("dedupe_key", sa.String(255), nullable=True))
        batch.create_unique_constraint("uq_notification_dedupe_key", ["dedupe_key"])
        batch.create_foreign_key(
            "fk_notification_rule_id",
            "notification_rules",
            ["rule_id"],
            ["id"],
        )

    # --- 6. messages: unique(conversation_id, client_msg_id) ---
    # Both SQLite and Postgres treat NULL as distinct in unique constraints,
    # so rows with NULL client_msg_id are unaffected.
    with op.batch_alter_table("messages") as batch:
        batch.create_unique_constraint(
            "uq_message_conversation_client_msg",
            ["conversation_id", "client_msg_id"],
        )

    # --- 6b. nudge_schedules: add linked_rule_id ---
    with op.batch_alter_table("nudge_schedules") as batch:
        batch.add_column(sa.Column("linked_rule_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_nudge_schedule_linked_rule",
            "notification_rules",
            ["linked_rule_id"],
            ["id"],
        )

    # --- 7. Migrate nudge_schedules → notification_rules + state ---
    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            "SELECT id, membership_id, topic, cron_rule, is_active, created_at "
            "FROM nudge_schedules"
        )
    ).fetchall()
    for row in rows:
        ns_id, membership_id, topic, cron_rule, is_active, created_at = row
        import json

        config_json = json.dumps({"topic": topic, "time": cron_rule})
        result = conn.execute(
            sa.text(
                "INSERT INTO notification_rules "
                "(membership_id, kind, config_json, tz_policy, is_active, created_at, updated_at) "
                "VALUES (:mid, 'daily_local_time', :cfg, 'floating_user_tz', :active, :cat, :cat)"
            ),
            {
                "mid": membership_id,
                "cfg": config_json,
                "active": is_active,
                "cat": created_at,
            },
        )
        # Retrieve the auto-generated id
        if _is_sqlite():
            rule_id = result.lastrowid
        else:
            rule_id = conn.execute(
                sa.text(
                    "SELECT currval(pg_get_serial_sequence('notification_rules', 'id'))"
                )
            ).scalar()

        if rule_id:
            # Link the nudge schedule to the new rule
            conn.execute(
                sa.text(
                    "UPDATE nudge_schedules SET linked_rule_id = :rid WHERE id = :nsid"
                ),
                {"rid": rule_id, "nsid": ns_id},
            )
            if is_active:
                conn.execute(
                    sa.text(
                        "INSERT INTO notification_rule_state (rule_id, attempts, updated_at) "
                        "VALUES (:rid, 0, :cat)"
                    ),
                    {"rid": rule_id, "cat": created_at},
                )


def downgrade() -> None:
    with op.batch_alter_table("nudge_schedules") as batch:
        batch.drop_constraint("fk_nudge_schedule_linked_rule", type_="foreignkey")
        batch.drop_column("linked_rule_id")

    with op.batch_alter_table("messages") as batch:
        batch.drop_constraint("uq_message_conversation_client_msg", type_="unique")

    with op.batch_alter_table("notifications") as batch:
        batch.drop_constraint("fk_notification_rule_id", type_="foreignkey")
        batch.drop_constraint("uq_notification_dedupe_key", type_="unique")
        batch.drop_column("dedupe_key")
        batch.drop_column("local_date")
        batch.drop_column("rule_id")

    op.drop_table("notification_deliveries")
    op.drop_table("notification_rule_state")
    op.drop_table("notification_rules")

    with op.batch_alter_table("flow_user_profiles") as batch:
        batch.drop_column("tz_offset_minutes")
        batch.drop_column("tz_updated_at")
        batch.drop_column("timezone")
