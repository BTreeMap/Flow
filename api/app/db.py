"""Async database engine, session factory, and helpers."""

from __future__ import annotations

from pathlib import Path
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app import config
from app.models import Base

_DATABASE_URL = config.get_database_url()

# Ensure the data directory exists for SQLite
if "sqlite" in _DATABASE_URL:
    _db_path = _DATABASE_URL.split("///")[-1] if "///" in _DATABASE_URL else ""
    if _db_path:
        Path(_db_path).parent.mkdir(parents=True, exist_ok=True)

engine = create_async_engine(_DATABASE_URL, echo=False)

async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async database session."""
    async with async_session_factory() as session:
        yield session


async def init_db() -> None:
    """Create all tables defined by the declarative base."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
