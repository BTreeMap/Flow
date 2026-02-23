"""Alembic environment configuration for Flow tables.

Uses a *sync* database URL (Alembic runs synchronous DDL).  The async URL
from the environment is normalised to its sync equivalent automatically by
:func:`app.db_migrations.migrate.get_sync_url`.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

VERSION_TABLE = "flow_alembic_version"


def _resolve_url() -> str:
    """Return the sync database URL.

    Priority:
    1. ``sqlalchemy.url`` already set on the Alembic config (set by the
       programmatic runner in ``migrate.py``).
    2. ``H4CKATH0N_DATABASE_URL`` env-var, converted to a sync driver.
    """
    url = config.get_main_option("sqlalchemy.url")
    if url:
        return url
    # Fallback: read from env and convert inline
    from app.db_migrations.migrate import get_sync_url

    return get_sync_url()


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode — emit SQL without a live connection."""
    context.configure(
        url=_resolve_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table=VERSION_TABLE,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live database connection."""
    cfg = config.get_section(config.config_ini_section, {})
    cfg["sqlalchemy.url"] = _resolve_url()

    connectable = engine_from_config(
        cfg,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            version_table=VERSION_TABLE,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
