"""Tests for POST /me/timezone endpoint."""

from __future__ import annotations

from typing import Any, AsyncGenerator
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models import Base, FlowUserProfile
from h4ckath0n.auth.models import Base as H4ckath0nBase

_test_engine = create_async_engine("sqlite+aiosqlite://", echo=False)
_test_session_factory = async_sessionmaker(_test_engine, expire_on_commit=False)


async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
    async with _test_session_factory() as session:
        yield session


def _override_require_user(
    user_id: str = "u_tz_endpoint_test_00000000000", role: str = "user"
) -> Any:
    fake = MagicMock()
    fake.id = user_id
    fake.role = role
    fake.email = "test@example.com"

    async def _dep() -> Any:
        return fake

    return _dep


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    from app.main import app
    from app.db import get_db
    from h4ckath0n.auth.dependencies import _get_current_user

    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(H4ckath0nBase.metadata.create_all)

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[_get_current_user] = _override_require_user()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(H4ckath0nBase.metadata.drop_all)


@pytest.mark.asyncio
async def test_set_timezone(client: AsyncClient) -> None:
    """POST /me/timezone stores a valid IANA timezone."""
    resp = await client.post(
        "/me/timezone",
        json={"timezone": "America/Toronto", "offset_minutes": -300},
    )
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}

    # Verify stored
    async with _test_session_factory() as db:
        result = await db.execute(
            select(FlowUserProfile).where(
                FlowUserProfile.user_id == "u_tz_endpoint_test_00000000000"
            )
        )
        profile = result.scalar_one()
        assert profile.timezone == "America/Toronto"
        assert profile.tz_offset_minutes == -300
        assert profile.tz_updated_at is not None


@pytest.mark.asyncio
async def test_set_timezone_upsert(client: AsyncClient) -> None:
    """POST /me/timezone creates profile if missing, updates if exists."""
    # First call: creates profile
    resp1 = await client.post(
        "/me/timezone",
        json={"timezone": "America/Toronto"},
    )
    assert resp1.status_code == 200

    # Second call: updates timezone
    resp2 = await client.post(
        "/me/timezone",
        json={"timezone": "Europe/London", "offset_minutes": 0},
    )
    assert resp2.status_code == 200

    async with _test_session_factory() as db:
        result = await db.execute(
            select(FlowUserProfile).where(
                FlowUserProfile.user_id == "u_tz_endpoint_test_00000000000"
            )
        )
        profile = result.scalar_one()
        assert profile.timezone == "Europe/London"
        assert profile.tz_offset_minutes == 0


@pytest.mark.asyncio
async def test_set_timezone_invalid(client: AsyncClient) -> None:
    """POST /me/timezone rejects invalid IANA timezone names."""
    resp = await client.post(
        "/me/timezone",
        json={"timezone": "Narnia/Lamppost"},
    )
    assert resp.status_code == 422
    assert "Invalid IANA timezone" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_set_timezone_offset_optional(client: AsyncClient) -> None:
    """offset_minutes is optional."""
    resp = await client.post(
        "/me/timezone",
        json={"timezone": "Asia/Tokyo"},
    )
    assert resp.status_code == 200

    async with _test_session_factory() as db:
        result = await db.execute(
            select(FlowUserProfile).where(
                FlowUserProfile.user_id == "u_tz_endpoint_test_00000000000"
            )
        )
        profile = result.scalar_one()
        assert profile.timezone == "Asia/Tokyo"
        assert profile.tz_offset_minutes is None
