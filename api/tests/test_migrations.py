"""Tests for Alembic migration infrastructure.

FIX 1: get_sync_url() mapping
FIX 3: Migration smoke tests (SQLite file-based + optional Postgres)
"""

from __future__ import annotations

import os
import tempfile

import pytest
from sqlalchemy import create_engine, inspect, text

from app.db_migrations.migrate import get_sync_url, upgrade_to_head


# ---------------------------------------------------------------------------
# FIX 1: get_sync_url mapping tests
# ---------------------------------------------------------------------------


class TestGetSyncUrl:
    def test_asyncpg_maps_to_psycopg(self) -> None:
        result = get_sync_url("postgresql+asyncpg://user:pass@host:5432/db")
        assert result == "postgresql+psycopg://user:pass@host:5432/db"

    def test_aiosqlite_maps_to_sqlite(self) -> None:
        result = get_sync_url("sqlite+aiosqlite:///path/to/db.sqlite")
        assert result == "sqlite:///path/to/db.sqlite"

    def test_already_sync_postgres_unchanged(self) -> None:
        url = "postgresql+psycopg://user:pass@host/db"
        assert get_sync_url(url) == url

    def test_already_sync_sqlite_unchanged(self) -> None:
        url = "sqlite:///path/to/db.sqlite"
        assert get_sync_url(url) == url

    def test_in_memory_sqlite(self) -> None:
        result = get_sync_url("sqlite+aiosqlite://")
        assert result == "sqlite://"

    def test_bare_postgresql_unchanged(self) -> None:
        url = "postgresql://user:pass@host/db"
        assert get_sync_url(url) == url


# ---------------------------------------------------------------------------
# FIX 3: Migration smoke tests
# ---------------------------------------------------------------------------

# Expected Flow tables created by migrations
_EXPECTED_TABLES = {
    "projects",
    "project_invites",
    "project_memberships",
    "participant_contacts",
    "conversations",
    "messages",
    "conversation_runtime_state",
    "push_subscriptions",
    "outbox_events",
    "user_profiles",
    "memory_items",
    "patch_audit_log",
    "conversation_events",
    "conversation_turns",
    "flow_user_profiles",
    "flow_alembic_version",
}


class TestMigrationSmokeSQLite:
    """Run Alembic upgrade head on a fresh file-based SQLite database."""

    def test_upgrade_creates_expected_tables(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_migration.db")
            sync_url = f"sqlite:///{db_path}"

            upgrade_to_head(sync_url=sync_url)

            engine = create_engine(sync_url)
            inspector = inspect(engine)
            tables = set(inspector.get_table_names())
            engine.dispose()

            missing = _EXPECTED_TABLES - tables
            assert not missing, f"Missing tables after migration: {missing}"

    def test_schema_is_functional(self) -> None:
        """Insert a row into a key table to confirm the schema works."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_migration_func.db")
            sync_url = f"sqlite:///{db_path}"

            upgrade_to_head(sync_url=sync_url)

            engine = create_engine(sync_url)
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "INSERT INTO projects (id, status, created_at) "
                        "VALUES (:id, 'active', datetime('now'))"
                    ),
                    {"id": "p_test_migration_000000000000"},
                )
                result = conn.execute(
                    text("SELECT id FROM projects WHERE id = :id"),
                    {"id": "p_test_migration_000000000000"},
                )
                row = result.fetchone()
            engine.dispose()

            assert row is not None
            assert row[0] == "p_test_migration_000000000000"


@pytest.mark.skipif(
    "postgresql" not in os.environ.get("H4CKATH0N_DATABASE_URL", ""),
    reason="Postgres not configured (H4CKATH0N_DATABASE_URL does not contain 'postgresql')",
)
class TestMigrationSmokePostgres:
    """Run Alembic upgrade head on Postgres (CI only)."""

    def test_upgrade_creates_expected_tables(self) -> None:
        async_url = os.environ["H4CKATH0N_DATABASE_URL"]
        sync_url = get_sync_url(async_url)
        upgrade_to_head(sync_url=sync_url)

        engine = create_engine(sync_url)
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        engine.dispose()

        missing = _EXPECTED_TABLES - tables
        assert not missing, f"Missing tables after migration: {missing}"
