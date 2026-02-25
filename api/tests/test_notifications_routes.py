from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any, AsyncGenerator
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.id_utils import generate_project_id
from app.models import (
    Base,
    FlowUserProfile,
    Notification,
    Project,
    ProjectInvite,
    ProjectMembership,
)
from h4ckath0n.auth.models import Base as H4ckath0nBase
from h4ckath0n.realtime import AuthContext

_test_engine = create_async_engine("sqlite+aiosqlite://", echo=False)
_test_session_factory = async_sessionmaker(_test_engine, expire_on_commit=False)


async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
    async with _test_session_factory() as session:
        yield session


def _make_fake_user(
    user_id: str = "u_testuser_000000000000000000", role: str = "user"
) -> MagicMock:
    user = MagicMock()
    user.id = user_id
    user.role = role
    user.email = "test@example.com"
    return user


def _override_require_user(
    user_id: str = "u_testuser_000000000000000000", role: str = "user"
) -> Any:
    fake = _make_fake_user(user_id, role=role)

    async def _dep() -> Any:
        return fake

    return _dep


def _override_auth_context(
    user_id: str = "u_testuser_000000000000000000", device_id: str = "d_test"
) -> Any:
    async def _dep() -> AuthContext:
        return AuthContext(user_id=user_id, device_id=device_id)

    return _dep


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    from app.main import app
    from app.db import get_db
    from app.routes import _require_auth_context
    from h4ckath0n.auth.dependencies import _get_current_user

    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(H4ckath0nBase.metadata.create_all)

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[_get_current_user] = _override_require_user()
    app.dependency_overrides[_require_auth_context] = _override_auth_context()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(H4ckath0nBase.metadata.drop_all)


@pytest_asyncio.fixture
async def seeded_project(client: AsyncClient) -> dict[str, Any]:
    project_id = generate_project_id()
    invite_code = "test-invite"
    code_hash = hashlib.sha256(invite_code.encode()).hexdigest()

    async with _test_session_factory() as db:
        project = Project(id=project_id, display_name="Test Project")
        db.add(project)
        invite = ProjectInvite(
            project_id=project_id,
            invite_code_hash=code_hash,
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
        db.add(invite)
        db.add(
            FlowUserProfile(
                user_id="u_testuser_000000000000000000", email_raw="test@example.com"
            )
        )
        await db.commit()

    # Activate
    await client.post(
        f"/p/{project_id}/activate/claim", json={"invite_code": invite_code}
    )

    return {"project_id": project_id, "client": client}


@pytest.mark.asyncio
async def test_notifications_lifecycle(seeded_project: dict[str, Any]) -> None:
    client = seeded_project["client"]
    project_id = seeded_project["project_id"]

    # 1. Create a notification manually in DB (simulating worker)
    async with _test_session_factory() as db:
        membership_result = await db.execute(
            select(ProjectMembership).where(ProjectMembership.project_id == project_id)
        )
        membership = membership_result.scalar_one()

        notif = Notification(
            membership_id=membership.id,
            title="Test Notification",
            body="This is a test.",
            payload_json="{}",
        )
        db.add(notif)
        await db.commit()
        notif_id = notif.id

    # 2. List notifications
    resp = await client.get(f"/p/{project_id}/notifications")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["notifications"]) == 1
    assert data["notifications"][0]["id"] == notif_id
    assert data["notifications"][0]["read_at"] is None

    # 3. Get unread count
    resp = await client.get(f"/p/{project_id}/notifications/unread-count")
    assert resp.status_code == 200
    assert resp.json()["count"] == 1

    # 4. Mark read
    resp = await client.post(f"/p/{project_id}/notifications/{notif_id}/read")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    # 5. Verify read status
    resp = await client.get(f"/p/{project_id}/notifications")
    assert resp.json()["notifications"][0]["read_at"] is not None

    resp = await client.get(f"/p/{project_id}/notifications/unread-count")
    assert resp.json()["count"] == 0


@pytest.mark.asyncio
async def test_scheduler_tools(seeded_project: dict[str, Any]) -> None:

    import app.tools.scheduler_tools as scheduler_tools_module
    from app.tools.scheduler_tools import (
        schedule_nudge,
        list_schedules,
        delete_schedule,
    )

    # Monkeypatch the session factory in the tools module
    old_factory = scheduler_tools_module.async_session_factory
    scheduler_tools_module.async_session_factory = _test_session_factory

    try:
        project_id = seeded_project["project_id"]
        async with _test_session_factory() as db:
            membership_result = await db.execute(
                select(ProjectMembership).where(
                    ProjectMembership.project_id == project_id
                )
            )
            membership = membership_result.scalar_one()
            membership_id = membership.id

        # Schedule
        res = await schedule_nudge.ainvoke(
            {"membership_id": membership_id, "topic": "Test Nudge", "time": "09:00"}
        )
        assert "Scheduled nudge ID" in res

        # List
        res = await list_schedules.ainvoke({"membership_id": membership_id})
        assert "Test Nudge" in res
        assert "09:00" in res

        # Parse ID from list
        # "ID: 1, Topic: ..."
        import re

        match = re.search(r"ID: (\d+)", res)
        schedule_id = int(match.group(1))

        # Delete
        res = await delete_schedule.ainvoke({"schedule_id": schedule_id})
        assert "deactivated" in res

        # List again
        res = await list_schedules.ainvoke({"membership_id": membership_id})
        assert "No active schedules found" in res

    finally:
        scheduler_tools_module.async_session_factory = old_factory
