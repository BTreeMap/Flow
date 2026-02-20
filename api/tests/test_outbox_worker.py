from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models import (
    Base,
    Conversation,
    Message,
    OutboxEvent,
    Project,
    ProjectMembership,
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
        event_type="scheduled_prompt",
        payload={"project_id": project_id},
        dedupe_key=f"scheduled_prompt:{membership_id}:2099-01-01",
        available_at=now,
    )
    await enqueue_outbox_event(
        db,
        project_id=str(project_id),
        membership_id=int(membership_id),
        event_type="scheduled_prompt",
        payload={"project_id": project_id},
        dedupe_key=f"scheduled_prompt:{membership_id}:2099-01-01",
        available_at=now,
    )
    await db.commit()

    result = await db.execute(select(OutboxEvent))
    assert len(result.scalars().all()) == 1


@pytest.mark.asyncio
async def test_worker_processes_scheduled_prompt_and_push_mock(
    db: AsyncSession, seeded: dict[str, int | str], monkeypatch
) -> None:
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

    async def fake_push(*args, **kwargs):  # type: ignore[no-untyped-def]
        return None

    monkeypatch.setattr("app.worker.outbox_worker._send_push_for_membership", fake_push)
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
        assert "Daily check-in" in messages[0].content

        outbox_result = await verify_db.execute(select(OutboxEvent))
        remaining = outbox_result.scalars().all()
        assert any(item.dedupe_key != event.dedupe_key for item in remaining)


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
            type="scheduled_prompt",
            payload_json='{"project_id":"%s"}' % project_id,
            dedupe_key=f"scheduled_prompt:{membership_id}:2099-01-02",
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
