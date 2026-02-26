from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import AsyncGenerator
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.id_utils import generate_project_id
from app.models import (
    Base,
    FlowUserProfile,
    OutboxEvent,
    Project,
    ProjectMembership,
)
from app.worker.outbox_worker import _handle_read_receipt

_test_engine = create_async_engine("sqlite+aiosqlite://", echo=False)
_test_session_factory = async_sessionmaker(_test_engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with _test_session_factory() as session:
        yield session
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.mark.asyncio
async def test_handle_read_receipt(db_session: AsyncSession) -> None:
    project_id = generate_project_id()
    project = Project(id=project_id, display_name="Test Project")
    db_session.add(project)

    membership = ProjectMembership(
        project_id=project_id, user_id="u_test", status="active"
    )
    db_session.add(membership)
    db_session.add(FlowUserProfile(user_id="u_test", email_raw="test@example.com"))
    await db_session.flush()

    event = OutboxEvent(
        project_id=project_id,
        membership_id=membership.id,
        type="notification_read_receipt",
        payload_json=json.dumps({"notification_id": 123, "project_id": project_id}),
        dedupe_key="read-receipt-123",
        available_at=datetime.now(UTC),
    )
    db_session.add(event)
    await db_session.commit()

    with patch(
        "app.worker.outbox_worker._send_push_notifications", new_callable=AsyncMock
    ) as mock_push:
        await _handle_read_receipt(db_session, event)

        mock_push.assert_called_once()
        args, kwargs = mock_push.call_args
        assert kwargs["data"]["action"] == "dismiss"
        assert kwargs["data"]["notification_id"] == 123
        assert kwargs["url"] == ""  # Silent push
