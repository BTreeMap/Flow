from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import AsyncGenerator
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select, func
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
    Message,
    Conversation,
)
from app.worker.outbox_worker import _handle_scheduled_nudge, _handle_read_receipt
from app.tools.scheduler_tools import schedule_nudge

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
async def test_full_nudge_lifecycle(db_session: AsyncSession) -> None:
    # 1. Setup Data
    project_id = generate_project_id()
    db_session.add(Project(id=project_id, display_name="Test Project"))
    membership = ProjectMembership(
        project_id=project_id, user_id="u_test", status="active"
    )
    db_session.add(membership)
    db_session.add(FlowUserProfile(user_id="u_test", email_raw="test@example.com"))
    await db_session.commit()

    # 2. Schedule Nudge (Agent Tool)
    # Patch session factory for the tool
    import app.tools.scheduler_tools as scheduler_tools_module

    old_factory = scheduler_tools_module.async_session_factory
    scheduler_tools_module.async_session_factory = _test_session_factory

    try:
        await schedule_nudge.ainvoke(
            {
                "membership_id": membership.id,
                "topic": "Morning Reflection",
                "time": "08:00",
            }
        )
    finally:
        scheduler_tools_module.async_session_factory = old_factory

    # Verify Schedule and Initial Event
    schedule = (await db_session.execute(select(NudgeSchedule))).scalar_one()
    assert schedule.topic == "Morning Reflection"
    assert schedule.cron_rule == "08:00"

    event = (
        await db_session.execute(
            select(OutboxEvent).where(OutboxEvent.type == "scheduled_nudge")
        )
    ).scalar_one()
    payload = json.loads(event.payload_json)
    assert payload["schedule_id"] == schedule.id

    # 3. Process Nudge (Worker)
    # We need to ensure the worker calculates the NEXT run time (e.g. tomorrow),
    # distinct from the current event's time, to avoid dedupe collision.
    future_run = event.available_at + timedelta(days=1)

    with (
        patch(
            "app.worker.outbox_worker._generate_custom_prompt", new_callable=AsyncMock
        ) as mock_llm,
        patch(
            "app.worker.outbox_worker._send_push_notifications", new_callable=AsyncMock
        ) as mock_push,
        patch("app.worker.outbox_worker.next_run_at", return_value=future_run),
    ):
        mock_llm.return_value = "Good morning! How are you feeling?"

        await _handle_scheduled_nudge(db_session, event)

        # Verify Notification & Message created atomically
        notification = (await db_session.execute(select(Notification))).scalar_one()
        assert notification.title == "Morning Reflection"
        assert notification.body == "Good morning! How are you feeling?"

        message = (
            await db_session.execute(select(Message).where(Message.role == "assistant"))
        ).scalar_one()
        assert message.content == "Good morning! How are you feeling?"

        # Verify Linkage (via payload or dedupe key logic if applicable, but mainly check push URL)
        args, kwargs = mock_push.call_args
        assert f"nid={notification.id}" in kwargs["url"]

        # Verify Next Recurrence Enqueued
        next_events = (
            (
                await db_session.execute(
                    select(OutboxEvent).where(
                        OutboxEvent.type == "scheduled_nudge",
                        OutboxEvent.id != event.id,
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(next_events) == 1

    # 4. Read Receipt (Simulate API enqueueing event -> Worker processing)
    read_event = OutboxEvent(
        project_id=project_id,
        membership_id=membership.id,
        type="notification_read_receipt",
        payload_json=json.dumps(
            {"notification_id": notification.id, "project_id": project_id}
        ),
        dedupe_key=f"read-receipt-{notification.id}",
        available_at=datetime.now(UTC),
    )

    with patch(
        "app.worker.outbox_worker._send_push_notifications", new_callable=AsyncMock
    ) as mock_push_receipt:
        await _handle_read_receipt(db_session, read_event)

        mock_push_receipt.assert_called_once()
        _, kwargs = mock_push_receipt.call_args
        assert kwargs["data"]["action"] == "dismiss"
        assert kwargs["data"]["notification_id"] == notification.id


@pytest.mark.asyncio
async def test_nudge_creates_conversation_if_missing(db_session: AsyncSession) -> None:
    # Setup without conversation
    project_id = generate_project_id()
    db_session.add(Project(id=project_id))
    membership = ProjectMembership(project_id=project_id, user_id="u_test_2")
    db_session.add(membership)
    db_session.add(FlowUserProfile(user_id="u_test_2"))
    await db_session.commit()

    event = OutboxEvent(
        project_id=project_id,
        membership_id=membership.id,
        type="scheduled_nudge",
        payload_json=json.dumps({"topic": "Test", "project_id": project_id}),
        dedupe_key="test-dedupe",
        available_at=datetime.now(UTC),
    )

    with (
        patch(
            "app.worker.outbox_worker._generate_custom_prompt", new_callable=AsyncMock
        ) as mock_llm,
        patch(
            "app.worker.outbox_worker._send_push_notifications", new_callable=AsyncMock
        ),
    ):
        mock_llm.return_value = "Prompt"
        await _handle_scheduled_nudge(db_session, event)

        # Verify conversation created
        conv_count = (
            await db_session.execute(
                select(func.count(Conversation.id)).where(
                    Conversation.membership_id == membership.id
                )
            )
        ).scalar()
        assert conv_count == 1

        # Verify message added
        msg_count = (await db_session.execute(select(func.count(Message.id)))).scalar()
        assert msg_count == 1
