from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app import config
from app.id_utils import generate_project_id
from app.models import (
    Base,
    ConversationEvent,
    Message,
    Notification,
    NotificationDelivery,
    NotificationRule,
    NotificationRuleState,
    Project,
    ProjectMembership,
    ScheduledTask,
)
from app.worker.notification_worker import _process_rule, _process_scheduled_tasks

_engine = create_async_engine("sqlite+aiosqlite://", echo=False)
_session_factory = async_sessionmaker(_engine, expire_on_commit=False)


@pytest_asyncio.fixture(autouse=True)
async def _db_schema() -> AsyncGenerator[None, None]:
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture(autouse=True)
def _clear_config_cache() -> None:
    config.clear_config_cache()


@pytest_asyncio.fixture
async def seeded_membership(monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    from app.worker import notification_worker as worker_module

    monkeypatch.setattr(worker_module, "async_session_factory", _session_factory)

    async def _fake_generate_custom_prompt(*args, **kwargs) -> str:
        return "Take a 1-minute action now."

    monkeypatch.setattr(
        worker_module, "_generate_custom_prompt", _fake_generate_custom_prompt
    )

    async with _session_factory() as db:
        project = Project(id=generate_project_id(), display_name="Worker Test Project")
        db.add(project)
        membership = ProjectMembership(
            project_id=project.id,
            user_id="u_worker_test_0000000000000000",
            status="active",
        )
        db.add(membership)
        await db.flush()

        rule = NotificationRule(
            membership_id=membership.id,
            kind="daily_local_time",
            config_json=json.dumps({"topic": "Daily Nudge", "time": "08:00"}),
            tz_policy="floating_user_tz",
            is_active=True,
        )
        db.add(rule)
        await db.flush()
        state = NotificationRuleState(
            rule_id=rule.id,
            next_due_at_utc=datetime.now(UTC) - timedelta(minutes=1),
            locked_by="worker-test",
            locked_until=datetime.now(UTC) + timedelta(minutes=5),
            claimed_at=datetime.now(UTC),
        )
        db.add(state)
        await db.commit()
        return {"membership_id": membership.id, "rule_id": rule.id}


@pytest.mark.asyncio
async def test_process_rule_enqueues_feedback_task_when_enabled(
    seeded_membership: dict[str, int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENABLE_AUTOMATED_FEEDBACK", "true")
    monkeypatch.setenv("FEEDBACK_DELAY_MINUTES", "30")
    monkeypatch.setenv("FEEDBACK_PROMPT_TEXT", "How did this nudge feel?")
    monkeypatch.setenv("FEEDBACK_OPTIONS", "Great,Needs changes,Ignored")
    config.clear_config_cache()

    await _process_rule(seeded_membership["rule_id"], "worker-test")

    async with _session_factory() as db:
        notif = (
            await db.execute(select(Notification).order_by(Notification.id.desc()))
        ).scalar_one()
        event = (
            await db.execute(
                select(ConversationEvent).where(
                    ConversationEvent.event_type == "message.final"
                )
            )
        ).scalar_one_or_none()
        assert event is not None
        task = (
            await db.execute(
                select(ScheduledTask).where(
                    ScheduledTask.parent_instance_id == notif.id,
                    ScheduledTask.rule_id == seeded_membership["rule_id"],
                )
            )
        ).scalar_one()
        payload = json.loads(task.payload_json)
        assert task.task_type == "feedback_request"
        assert payload["text"] == "How did this nudge feel?"
        # Web Push actions are intentionally capped to 2 options for broad browser/OS parity.
        assert payload["actions"] == [
            {"action": "fb_0", "title": "Great"},
            {"action": "fb_1", "title": "Needs changes"},
        ]


@pytest.mark.asyncio
async def test_process_rule_does_not_enqueue_feedback_task_when_disabled(
    seeded_membership: dict[str, int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENABLE_AUTOMATED_FEEDBACK", "false")
    config.clear_config_cache()

    await _process_rule(seeded_membership["rule_id"], "worker-test")

    async with _session_factory() as db:
        tasks = (await db.execute(select(ScheduledTask))).scalars().all()
        assert tasks == []


@pytest.mark.asyncio
async def test_process_scheduled_tasks_creates_message_notification_and_delivery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.worker import notification_worker as worker_module

    monkeypatch.setattr(worker_module, "async_session_factory", _session_factory)

    async with _session_factory() as db:
        project = Project(
            id=generate_project_id(), display_name="Task Execution Project"
        )
        db.add(project)
        membership = ProjectMembership(
            project_id=project.id,
            user_id="u_worker_exec_0000000000000000",
            status="active",
        )
        db.add(membership)
        await db.flush()

        parent_notification = Notification(
            membership_id=membership.id,
            title="Daily Nudge",
            body="Do your habit now",
            payload_json="{}",
        )
        db.add(parent_notification)
        await db.flush()

        task = ScheduledTask(
            membership_id=membership.id,
            parent_instance_id=parent_notification.id,
            task_type="feedback_request",
            payload_json=json.dumps(
                {
                    "text": "How did this prompt work for you?",
                    "actions": [
                        {"action": "fb_0", "title": "Works perfectly"},
                        {"action": "fb_1", "title": "Needs tweaks"},
                    ],
                }
            ),
            run_at_utc=datetime.now(UTC) - timedelta(minutes=1),
            status="pending",
        )
        db.add(task)
        await db.commit()
        task_id = task.id

    processed = await _process_scheduled_tasks("worker-test")
    assert processed == 1

    async with _session_factory() as db:
        updated_task = (
            await db.execute(select(ScheduledTask).where(ScheduledTask.id == task_id))
        ).scalar_one()
        assert updated_task.status == "completed"
        event = (
            await db.execute(
                select(ConversationEvent).where(
                    ConversationEvent.event_type == "message.final"
                )
            )
        ).scalar_one_or_none()
        assert event is not None

        feedback_msg = (
            await db.execute(
                select(Message).where(Message.client_msg_id == f"feedback:{task_id}")
            )
        ).scalar_one()
        assert feedback_msg.role == "assistant"
        assert feedback_msg.metadata_ is not None
        assert feedback_msg.metadata_["type"] == "feedback_poll"
        assert feedback_msg.metadata_["status"] == "pending"
        assert feedback_msg.metadata_["notification_id"] > 0
        assert feedback_msg.metadata_["actions"] == [
            {"id": "fb_0", "title": "Works perfectly"},
            {"id": "fb_1", "title": "Needs tweaks"},
        ]

        feedback_notif = (
            await db.execute(
                select(Notification).where(
                    Notification.dedupe_key == f"feedback:{task_id}"
                )
            )
        ).scalar_one()

        delivery = (
            await db.execute(
                select(NotificationDelivery).where(
                    NotificationDelivery.instance_id == feedback_notif.id
                )
            )
        ).scalar_one()
        payload = json.loads(delivery.payload_json)
        assert payload["actions"] == [
            {"action": "fb_0", "title": "Works perfectly"},
            {"action": "fb_1", "title": "Needs tweaks"},
        ]
        assert payload["data"]["action"] == "feedback"
        assert payload["url"].endswith(f"/chat?nid={feedback_notif.id}")


@pytest.mark.asyncio
async def test_process_scheduled_tasks_cancels_task_when_parent_rule_inactive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.worker import notification_worker as worker_module

    monkeypatch.setattr(worker_module, "async_session_factory", _session_factory)

    async with _session_factory() as db:
        project = Project(
            id=generate_project_id(), display_name="Inactive Rule Project"
        )
        db.add(project)
        membership = ProjectMembership(
            project_id=project.id,
            user_id="u_worker_inactive_rule_000000",
            status="active",
        )
        db.add(membership)
        await db.flush()

        rule = NotificationRule(
            membership_id=membership.id,
            kind="daily_local_time",
            config_json=json.dumps({"topic": "Daily Nudge", "time": "08:00"}),
            tz_policy="floating_user_tz",
            is_active=False,
        )
        db.add(rule)
        await db.flush()

        task = ScheduledTask(
            membership_id=membership.id,
            rule_id=rule.id,
            task_type="feedback_request",
            payload_json=json.dumps(
                {
                    "text": "How did this prompt work for you?",
                    "actions": [
                        {"action": "fb_0", "title": "Works perfectly"},
                        {"action": "fb_1", "title": "Needs tweaks"},
                    ],
                }
            ),
            run_at_utc=datetime.now(UTC) - timedelta(minutes=1),
            status="pending",
        )
        db.add(task)
        await db.commit()
        task_id = task.id

    processed = await _process_scheduled_tasks("worker-test")
    assert processed == 0

    async with _session_factory() as db:
        updated_task = (
            await db.execute(select(ScheduledTask).where(ScheduledTask.id == task_id))
        ).scalar_one()
        assert updated_task.status == "cancelled"


@pytest.mark.asyncio
async def test_scheduled_task_deleted_when_parent_notification_deleted() -> None:
    async with _session_factory() as db:
        await db.execute(text("PRAGMA foreign_keys=ON"))
        project = Project(id=generate_project_id(), display_name="Cascade Project")
        db.add(project)
        membership = ProjectMembership(
            project_id=project.id,
            user_id="u_worker_cascade_0000000000000",
            status="active",
        )
        db.add(membership)
        await db.flush()

        notification = Notification(
            membership_id=membership.id,
            title="Nudge",
            body="Body",
            payload_json="{}",
        )
        db.add(notification)
        await db.flush()

        task = ScheduledTask(
            membership_id=membership.id,
            parent_instance_id=notification.id,
            task_type="feedback_request",
            payload_json="{}",
            run_at_utc=datetime.now(UTC) + timedelta(minutes=10),
        )
        db.add(task)
        await db.commit()

        task_id = task.id
        await db.delete(notification)
        await db.commit()

        remaining = await db.execute(
            select(ScheduledTask).where(ScheduledTask.id == task_id)
        )
        assert remaining.scalar_one_or_none() is None
