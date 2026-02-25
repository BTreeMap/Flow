"""Programmatic Alembic runner for Flow migrations.

Public helpers
--------------
- :func:`get_sync_url` – convert the async DATABASE_URL to a sync one.
- :func:`upgrade_to_head` – run ``alembic upgrade head``.
- :func:`stamp_head` – stamp the DB at head without running migrations.
"""

from __future__ import annotations

import logging
from pathlib import Path

from alembic import command
from alembic.config import Config

from app import config

logger = logging.getLogger(__name__)

_MIGRATIONS_DIR = Path(__file__).resolve().parent


def get_sync_url(async_url: str | None = None) -> str:
    """Return a synchronous database URL suitable for Alembic.

    Converts async driver prefixes to their sync equivalents:
    - ``sqlite+aiosqlite`` → ``sqlite``
    - ``postgresql+asyncpg`` → ``postgresql+psycopg``
    """
    if async_url is None:
        async_url = config.get_database_url()
    url = async_url.replace("sqlite+aiosqlite", "sqlite").replace(
        "postgresql+asyncpg", "postgresql+psycopg"
    )
    return url


def _make_config(sync_url: str | None = None) -> Config:
    """Build an :class:`alembic.config.Config` pointing at our migrations."""
    cfg = Config(str(_MIGRATIONS_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(_MIGRATIONS_DIR))
    if sync_url is None:
        sync_url = get_sync_url()
    cfg.set_main_option("sqlalchemy.url", sync_url)
    return cfg


def upgrade_to_head(sync_url: str | None = None) -> None:
    """Run ``alembic upgrade head`` programmatically."""
    cfg = _make_config(sync_url)
    logger.info("Running Alembic upgrade to head …")
    command.upgrade(cfg, "head")
    logger.info("Alembic upgrade complete.")


def stamp_head(sync_url: str | None = None) -> None:
    """Stamp the database at the current head revision without running migrations."""
    cfg = _make_config(sync_url)
    logger.info("Stamping Alembic head …")
    command.stamp(cfg, "head")
    logger.info("Alembic stamp complete.")
