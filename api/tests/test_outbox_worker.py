from __future__ import annotations
from datetime import UTC, datetime, timedelta
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import clear_config_cache
from app.models import (
    Base,
    Conversation,
    Message,
    Notification,
    NudgeSchedule,
    OutboxEvent,
    Project,
    ProjectMembership,
    PushSubscription,
)
from app.services.outbox_service import enqueue_outbox_event
from app.services.profile_service import save_user_profile
from app.schemas.patches import UserProfileData
from app.worker.outbox_worker import _claim_due_events, _process_event

_engine = create_async_engine("sqlite+aiosqlite://", echo=False)
_session_factory = async_sessionmaker(_engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def db() -> AsyncGenerator[AsyncSession, None]:
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with _session_factory() as session:
        yield session
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def seeded(db: AsyncSession) -> dict[str, int | str]:
    project = Project(id="p" + "a" * 31, display_name="Study")
    db.add(project)
    await db.flush()
    membership = ProjectMembership(
        project_id=project.id,
        user_id="u_seeded_00000000000000000000",
        status="active",
    )
    db.add(membership)
    await db.flush()
    db.add(Conversation(membership_id=membership.id))
    await save_user_profile(
        db,
        membership.id,
        UserProfileData(prompt_anchor="after coffee", preferred_time="08:00"),
    )
    await db.commit()
    return {"project_id": project.id, "membership_id": membership.id}


@pytest.mark.asyncio
async def test_enqueue_outbox_dedupe(
    db: AsyncSession, seeded: dict[str, int | str]
) -> None:
    project_id = seeded["project_id"]
    membership_id = seeded["membership_id"]
    now = datetime.now(UTC) + timedelta(minutes=10)
    await enqueue_outbox_event(
        db,
        project_id=str(project_id),
        membership_id=int(membership_id),
        event_type="scheduled_nudge",
        payload={"project_id": project_id, "topic": "Daily Nudge"},
        dedupe_key=f"nudge:{membership_id}:2099-01-01",
        available_at=now,
    )
    await enqueue_outbox_event(
        db,
        project_id=str(project_id),
        membership_id=int(membership_id),
        event_type="scheduled_nudge",
        payload={"project_id": project_id, "topic": "Daily Nudge"},
        dedupe_key=f"nudge:{membership_id}:2099-01-01",
        available_at=now,
    )
    await db.commit()

    result = await db.execute(select(OutboxEvent))
    assert len(result.scalars().all()) == 1


@pytest.mark.asyncio
async def test_worker_processes_scheduled_nudge(
    db: AsyncSession, seeded: dict[str, int | str], monkeypatch
) -> None:
    """scheduled_nudge processing persists one assistant message and one notification."""
    project_id = str(seeded["project_id"])
    membership_id = int(seeded["membership_id"])

    # Create a nudge schedule so recurrence gets enqueued
    schedule = NudgeSchedule(
        membership_id=membership_id, topic="Walk", cron_rule="08:00", is_active=True
    )
    db.add(schedule)
    await db.flush()

    import json

    event = OutboxEvent(
        project_id=project_id,
        membership_id=membership_id,
        type="scheduled_nudge",
        payload_json=json.dumps(
            {
                "project_id": project_id,
                "schedule_id": schedule.id,
                "topic": "Walk",
            }
        ),
        dedupe_key=f"nudge:{schedule.id}:2099-01-01",
        available_at=datetime.now(UTC),
        locked_by="worker-1",
        claimed_at=datetime.now(UTC),
        locked_until=datetime.now(UTC) + timedelta(minutes=1),
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)

    async def fake_push(*args, **kwargs):  # type: ignore[no-untyped-def]
        return None

    monkeypatch.setattr("app.worker.outbox_worker._send_push_notifications", fake_push)
    monkeypatch.setattr(
        "app.worker.outbox_worker._generate_custom_prompt", fake_generate
    )
    monkeypatch.setattr(
        "app.worker.outbox_worker.async_session_factory", _session_factory
    )
    await _process_event(event, worker_id="worker-1")

    async with _session_factory() as verify_db:
        message_result = await verify_db.execute(
            select(Message).where(Message.role == "assistant")
        )
        messages = message_result.scalars().all()
        assert len(messages) == 1

        notification_result = await verify_db.execute(select(Notification))
        notifications = notification_result.scalars().all()
        assert len(notifications) == 1

        # Recurrence event should have been enqueued
        outbox_result = await verify_db.execute(select(OutboxEvent))
        remaining = outbox_result.scalars().all()
        assert len(remaining) == 1
        assert remaining[0].type == "scheduled_nudge"
        assert remaining[0].dedupe_key != event.dedupe_key


async def fake_generate(db, membership_id: int, topic: str) -> str:
    return f"Nudge: {topic}"


@pytest.mark.asyncio
async def test_legacy_scheduled_prompt_is_noop(
    db: AsyncSession, seeded: dict[str, int | str], monkeypatch
) -> None:
    """A legacy scheduled_prompt event is silently deleted as a noop."""
    project_id = str(seeded["project_id"])
    membership_id = int(seeded["membership_id"])
    event = OutboxEvent(
        project_id=project_id,
        membership_id=membership_id,
        type="scheduled_prompt",
        payload_json='{"project_id":"%s"}' % project_id,
        dedupe_key=f"scheduled_prompt:{membership_id}:2099-01-01",
        available_at=datetime.now(UTC),
        locked_by="worker-1",
        claimed_at=datetime.now(UTC),
        locked_until=datetime.now(UTC) + timedelta(minutes=1),
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)

    monkeypatch.setattr(
        "app.worker.outbox_worker.async_session_factory", _session_factory
    )
    await _process_event(event, worker_id="worker-1")

    async with _session_factory() as verify_db:
        # No messages should have been created
        message_result = await verify_db.execute(
            select(Message).where(Message.role == "assistant")
        )
        assert message_result.scalars().all() == []

        # Event should be deleted
        event_result = await verify_db.execute(
            select(OutboxEvent).where(OutboxEvent.id == event.id)
        )
        assert event_result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_claim_due_events_prevents_double_claim(
    db: AsyncSession, seeded: dict[str, int | str], monkeypatch
) -> None:
    project_id = str(seeded["project_id"])
    membership_id = int(seeded["membership_id"])
    db.add(
        OutboxEvent(
            project_id=project_id,
            membership_id=membership_id,
            type="scheduled_nudge",
            payload_json='{"project_id":"%s","topic":"Walk"}' % project_id,
            dedupe_key=f"nudge:{membership_id}:2099-01-02",
            available_at=datetime.now(UTC),
        )
    )
    await db.commit()

    monkeypatch.setattr(
        "app.worker.outbox_worker.async_session_factory", _session_factory
    )
    claimed_by_worker_1 = await _claim_due_events(worker_id="worker-1")
    claimed_by_worker_2 = await _claim_due_events(worker_id="worker-2")

    assert len(claimed_by_worker_1) == 1
    assert claimed_by_worker_2 == []


@pytest.mark.asyncio
async def test_slow_push_times_out_without_duplicate_messages(
    db: AsyncSession, seeded: dict[str, int | str], monkeypatch
) -> None:
    """Push timeout must not cause the outbox event to retry."""
    project_id = str(seeded["project_id"])
    membership_id = int(seeded["membership_id"])

    schedule = NudgeSchedule(
        membership_id=membership_id, topic="Walk", cron_rule="08:00", is_active=True
    )
    db.add(schedule)
    await db.flush()

    import json

    event = OutboxEvent(
        project_id=project_id,
        membership_id=membership_id,
        type="scheduled_nudge",
        payload_json=json.dumps(
            {
                "project_id": project_id,
                "schedule_id": schedule.id,
                "topic": "Walk",
            }
        ),
        dedupe_key=f"nudge:{schedule.id}:2099-01-03",
        available_at=datetime.now(UTC),
        locked_by="worker-timeout",
        claimed_at=datetime.now(UTC),
        locked_until=datetime.now(UTC) + timedelta(minutes=5),
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)

    db.add(
        PushSubscription(
            membership_id=membership_id,
            endpoint="https://push.example.com/sub/slow",
            p256dh="pk",
            auth="ak",
            user_agent="pytest",
        )
    )
    await db.commit()

    def fake_slow_webpush(*args, **kwargs):  # type: ignore[no-untyped-def]
        import time

        time.sleep(0.05)
        return None

    monkeypatch.setenv("VAPID_PRIVATE_KEY", "test-private")
    monkeypatch.setenv("VAPID_PUBLIC_KEY", "test-public")
    clear_config_cache()
    monkeypatch.setattr("app.worker.outbox_worker.PUSH_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr("app.worker.outbox_worker.webpush", fake_slow_webpush)
    monkeypatch.setattr(
        "app.worker.outbox_worker._generate_custom_prompt", fake_generate
    )
    monkeypatch.setattr(
        "app.worker.outbox_worker.async_session_factory", _session_factory
    )

    await _process_event(event, worker_id="worker-timeout")

    async with _session_factory() as verify_db:
        # Message should still be persisted exactly once
        message_result = await verify_db.execute(
            select(Message).where(
                Message.role == "assistant",
                Message.client_msg_id == event.dedupe_key,
            )
        )
        messages = message_result.scalars().all()
        assert len(messages) == 1

        # Event should be deleted (not retried) despite push timeout
        event_result = await verify_db.execute(
            select(OutboxEvent).where(OutboxEvent.id == event.id)
        )
        assert event_result.scalar_one_or_none() is None
