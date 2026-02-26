from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import AsyncGenerator
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.id_utils import generate_project_id
from app.models import (
    Base,
    FlowUserProfile,
    Notification,
    NudgeSchedule,
    OutboxEvent,
    Project,
    ProjectMembership,
)
from app.worker.outbox_worker import _handle_scheduled_nudge

# Helper to create DB
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
async def test_handle_scheduled_nudge(db_session: AsyncSession) -> None:
    # Setup data
    project_id = generate_project_id()
    project = Project(id=project_id, display_name="Test Project")
    db_session.add(project)

    membership = ProjectMembership(
        project_id=project_id, user_id="u_test", status="active"
    )
    db_session.add(membership)
    db_session.add(FlowUserProfile(user_id="u_test", email_raw="test@example.com"))
    await db_session.flush()

    schedule = NudgeSchedule(
        membership_id=membership.id,
        topic="Test Topic",
        cron_rule="09:00",
        is_active=True,
    )
    db_session.add(schedule)
    await db_session.flush()

    event = OutboxEvent(
        project_id=project_id,
        membership_id=membership.id,
        type="scheduled_nudge",
        payload_json=json.dumps(
            {
                "schedule_id": schedule.id,
                "topic": "Test Topic",
                "project_id": project_id,
            }
        ),
        dedupe_key="test-dedupe",
        available_at=datetime.now(UTC),
    )
    db_session.add(event)
    await db_session.commit()

    # Mock LLM and Push
    with (
        patch(
            "app.worker.outbox_worker._generate_custom_prompt", new_callable=AsyncMock
        ) as mock_llm,
        patch(
            "app.worker.outbox_worker._send_push_notifications", new_callable=AsyncMock
        ) as mock_push,
    ):
        mock_llm.return_value = "Generated Nudge Content"

        await _handle_scheduled_nudge(db_session, event)

        # Verify Notification created
        result = await db_session.execute(
            select(Notification).where(Notification.membership_id == membership.id)
        )
        notif = result.scalar_one()
        assert notif.title == "Test Topic"
        assert notif.body == "Generated Nudge Content"

        # Verify Next Event Enqueued
        result = await db_session.execute(
            select(OutboxEvent).where(
                OutboxEvent.type == "scheduled_nudge", OutboxEvent.id != event.id
            )
        )
        next_event = result.scalar_one()
        payload = json.loads(next_event.payload_json)
        assert payload["schedule_id"] == schedule.id
        assert "nudge:" in next_event.dedupe_key

        # Verify Push called
        mock_push.assert_called_once()
        args, kwargs = mock_push.call_args
        assert kwargs["title"] == "Test Topic"
        assert kwargs["body"] == "Generated Nudge Content"
        assert kwargs["url"] == f"/p/{project_id}/chat?nid={notif.id}"


@pytest.mark.asyncio
async def test_handle_scheduled_nudge_inactive_schedule(
    db_session: AsyncSession,
) -> None:
    # Setup data
    project_id = generate_project_id()
    project = Project(id=project_id, display_name="Test Project")
    db_session.add(project)

    membership = ProjectMembership(
        project_id=project_id, user_id="u_test", status="active"
    )
    db_session.add(membership)
    db_session.add(FlowUserProfile(user_id="u_test", email_raw="test@example.com"))
    await db_session.flush()

    schedule = NudgeSchedule(
        membership_id=membership.id,
        topic="Test Topic",
        cron_rule="09:00",
        is_active=False,  # Inactive
    )
    db_session.add(schedule)
    await db_session.flush()

    event = OutboxEvent(
        project_id=project_id,
        membership_id=membership.id,
        type="scheduled_nudge",
        payload_json=json.dumps(
            {
                "schedule_id": schedule.id,
                "topic": "Test Topic",
                "project_id": project_id,
            }
        ),
        dedupe_key="test-dedupe",
        available_at=datetime.now(UTC),
    )
    db_session.add(event)
    await db_session.commit()

    with (
        patch(
            "app.worker.outbox_worker._generate_custom_prompt", new_callable=AsyncMock
        ),
        patch(
            "app.worker.outbox_worker._send_push_notifications", new_callable=AsyncMock
        ),
    ):
        await _handle_scheduled_nudge(db_session, event)

        # Verify NO Notification created (assuming inactive schedule stops everything? Or just recurrence?)
        # My implementation:
        # if not schedule or not schedule.is_active: return
        # So it returns immediately.

        result = await db_session.execute(
            select(Notification).where(Notification.membership_id == membership.id)
        )
        assert result.scalar_one_or_none() is None

        # Verify NO Next Event
        result = await db_session.execute(
            select(OutboxEvent).where(
                OutboxEvent.type == "scheduled_nudge", OutboxEvent.id != event.id
            )
        )
        assert result.scalar_one_or_none() is None
