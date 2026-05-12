"""Tests for the unified notification API and webpush endpoints."""

from __future__ import annotations

import hashlib
import json
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
    NotificationDelivery,
    NotificationRule,
    Project,
    ProjectInvite,
    ProjectMembership,
    PushSubscription,
    ScheduledTask,
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
                user_id="u_testuser_000000000000000000",
                email_raw="test@example.com",
                timezone="America/New_York",
            )
        )
        await db.commit()

    await client.post(
        f"/p/{project_id}/activate/claim", json={"invite_code": invite_code}
    )

    return {"project_id": project_id, "client": client}


# ---------------------------------------------------------------------------
# Unified notification endpoints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unified_notifications_lifecycle(seeded_project: dict[str, Any]) -> None:
    """GET /notifications returns items with project_id and project_name in one response."""
    client = seeded_project["client"]
    project_id = seeded_project["project_id"]

    async with _test_session_factory() as db:
        membership_result = await db.execute(
            select(ProjectMembership).where(ProjectMembership.project_id == project_id)
        )
        membership = membership_result.scalar_one()

        notif1 = Notification(
            membership_id=membership.id,
            title="Nudge 1",
            body="First nudge body.",
            payload_json="{}",
        )
        notif2 = Notification(
            membership_id=membership.id,
            title="Nudge 2",
            body="Second nudge body.",
            payload_json="{}",
        )
        db.add(notif1)
        db.add(notif2)
        await db.commit()
        notif1_id = notif1.id
        notif2_id = notif2.id

    # List unified notifications
    resp = await client.get("/notifications")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["notifications"]) == 2
    for n in data["notifications"]:
        assert n["project_id"] == project_id
        assert n["project_display_name"] == "Test Project"
        assert "membership_id" in n
        assert "payload_json" in n

    # Unread count
    resp = await client.get("/notifications/unread-count")
    assert resp.status_code == 200
    assert resp.json()["count"] == 2

    # Mark one read
    resp = await client.post(f"/notifications/{notif1_id}/read")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    # Verify unread count decreased
    resp = await client.get("/notifications/unread-count")
    assert resp.json()["count"] == 1

    # Verify the read status in unified list
    resp = await client.get("/notifications")
    notifications_data = {n["id"]: n for n in resp.json()["notifications"]}
    assert notifications_data[notif1_id]["read_at"] is not None
    assert notifications_data[notif2_id]["read_at"] is None


@pytest.mark.asyncio
async def test_unread_count_with_project_filter(
    seeded_project: dict[str, Any],
) -> None:
    """Unread count is correct with and without project_id filter."""
    client = seeded_project["client"]
    project_id = seeded_project["project_id"]

    async with _test_session_factory() as db:
        membership_result = await db.execute(
            select(ProjectMembership).where(ProjectMembership.project_id == project_id)
        )
        membership = membership_result.scalar_one()

        for i in range(3):
            db.add(
                Notification(
                    membership_id=membership.id,
                    title=f"Notif {i}",
                    body=f"Body {i}",
                    payload_json="{}",
                )
            )
        await db.commit()

    # Unread count without filter
    resp = await client.get("/notifications/unread-count")
    assert resp.json()["count"] == 3

    # Unread count with project filter
    resp = await client.get(
        "/notifications/unread-count", params={"project_id": project_id}
    )
    assert resp.json()["count"] == 3

    # Unread count with non-existent project filter
    resp = await client.get(
        "/notifications/unread-count", params={"project_id": "p_nonexistent_0000000"}
    )
    assert resp.json()["count"] == 0


@pytest.mark.asyncio
async def test_mark_read_enqueues_exactly_one_push_dismiss(
    seeded_project: dict[str, Any],
) -> None:
    """POST /notifications/{id}/read creates exactly ONE push_dismiss delivery."""
    client = seeded_project["client"]
    project_id = seeded_project["project_id"]

    async with _test_session_factory() as db:
        membership_result = await db.execute(
            select(ProjectMembership).where(ProjectMembership.project_id == project_id)
        )
        membership = membership_result.scalar_one()

        # Create multiple push subscriptions for this user
        for i in range(3):
            sub = PushSubscription(
                user_id="u_testuser_000000000000000000",
                endpoint=f"https://push.example.com/sub/{i}",
                p256dh=f"testkey{i}",
                auth=f"testauth{i}",
                user_agent="pytest",
            )
            db.add(sub)

        notif = Notification(
            membership_id=membership.id,
            title="Test",
            body="Body",
            payload_json="{}",
        )
        db.add(notif)
        await db.commit()
        notif_id = notif.id

    # Mark read
    resp = await client.post(f"/notifications/{notif_id}/read")
    assert resp.status_code == 200

    # Check exactly ONE delivery was created (not 3)
    async with _test_session_factory() as db:
        result = await db.execute(
            select(NotificationDelivery).where(
                NotificationDelivery.instance_id == notif_id,
                NotificationDelivery.channel == "push_dismiss",
            )
        )
        deliveries = result.scalars().all()
        assert len(deliveries) == 1
        payload = json.loads(deliveries[0].payload_json)
        assert payload["data"]["action"] == "dismiss"
        assert payload["data"]["notification_id"] == notif_id
        assert deliveries[0].user_id == "u_testuser_000000000000000000"


@pytest.mark.asyncio
async def test_unified_notification_read_not_found(
    seeded_project: dict[str, Any],
) -> None:
    """Reading a non-existent notification returns 404."""
    client = seeded_project["client"]
    resp = await client.post("/notifications/999999/read")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Web Push endpoints (user-scoped)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_webpush_vapid_key(client: AsyncClient) -> None:
    """GET /notifications/webpush/vapid-public-key returns 503 when not configured."""
    resp = await client.get("/notifications/webpush/vapid-public-key")
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_webpush_subscribe_and_list(
    seeded_project: dict[str, Any],
) -> None:
    """POST /notifications/webpush/subscriptions creates ONE user-scoped subscription."""
    client = seeded_project["client"]

    resp = await client.post(
        "/notifications/webpush/subscriptions",
        json={
            "endpoint": "https://push.example.com/sub/test",
            "keys": {"p256dh": "testkey123", "auth": "testauth123"},
            "user_agent": "pytest-browser",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["subscription_id"] > 0

    # List subscriptions
    resp = await client.get("/notifications/webpush/subscriptions")
    assert resp.status_code == 200
    subs = resp.json()["subscriptions"]
    assert len(subs) == 1
    assert subs[0]["endpoint"] == "https://push.example.com/sub/test"
    # User-scoped: no membership_id in response
    assert "membership_id" not in subs[0]


@pytest.mark.asyncio
async def test_webpush_subscribe_upserts(
    seeded_project: dict[str, Any],
) -> None:
    """Re-subscribing with same endpoint upserts keys."""
    client = seeded_project["client"]

    body: dict[str, Any] = {
        "endpoint": "https://push.example.com/sub/upsert",
        "keys": {"p256dh": "key1", "auth": "auth1"},
    }
    resp1 = await client.post("/notifications/webpush/subscriptions", json=body)
    sub_id_1 = resp1.json()["subscription_id"]

    body["keys"] = {"p256dh": "key2", "auth": "auth2"}
    resp2 = await client.post("/notifications/webpush/subscriptions", json=body)
    sub_id_2 = resp2.json()["subscription_id"]

    assert sub_id_1 == sub_id_2  # same subscription updated

    # Only one subscription in DB
    resp = await client.get("/notifications/webpush/subscriptions")
    assert len(resp.json()["subscriptions"]) == 1


@pytest.mark.asyncio
async def test_webpush_unsubscribe(
    seeded_project: dict[str, Any],
) -> None:
    """DELETE /notifications/webpush/subscriptions/{id} revokes subscription."""
    client = seeded_project["client"]

    resp = await client.post(
        "/notifications/webpush/subscriptions",
        json={
            "endpoint": "https://push.example.com/sub/delete-test",
            "keys": {"p256dh": "key", "auth": "auth"},
        },
    )
    sub_id = resp.json()["subscription_id"]

    resp = await client.request(
        "DELETE", f"/notifications/webpush/subscriptions/{sub_id}"
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    # List should be empty
    resp = await client.get("/notifications/webpush/subscriptions")
    assert len(resp.json()["subscriptions"]) == 0


@pytest.mark.asyncio
async def test_webpush_upsert_reactivates_revoked(
    seeded_project: dict[str, Any],
) -> None:
    """POST /notifications/webpush/subscriptions re-enables a revoked subscription."""
    client = seeded_project["client"]

    body: dict[str, Any] = {
        "endpoint": "https://push.example.com/sub/reactivate",
        "keys": {"p256dh": "key1", "auth": "auth1"},
    }
    resp = await client.post("/notifications/webpush/subscriptions", json=body)
    sub_id = resp.json()["subscription_id"]

    # Revoke it
    await client.request("DELETE", f"/notifications/webpush/subscriptions/{sub_id}")
    resp = await client.get("/notifications/webpush/subscriptions")
    assert len(resp.json()["subscriptions"]) == 0

    # Re-subscribe with same endpoint — should reactivate, not create new
    body["keys"] = {"p256dh": "key2", "auth": "auth2"}
    resp = await client.post("/notifications/webpush/subscriptions", json=body)
    sub_id_2 = resp.json()["subscription_id"]
    assert sub_id_2 == sub_id  # same row reactivated

    # Should be active again
    resp = await client.get("/notifications/webpush/subscriptions")
    subs = resp.json()["subscriptions"]
    assert len(subs) == 1
    assert subs[0]["id"] == sub_id


@pytest.mark.asyncio
async def test_push_subscription_consecutive_gone_410_count(
    seeded_project: dict[str, Any],
) -> None:
    """PushSubscription has consecutive_gone_410_count column defaulting to 0."""
    async with _test_session_factory() as db:
        sub = PushSubscription(
            user_id="u_testuser_000000000000000000",
            endpoint="https://push.example.com/sub/410test",
            p256dh="key",
            auth="auth",
            user_agent="pytest",
        )
        db.add(sub)
        await db.commit()
        assert sub.consecutive_gone_410_count == 0


# ---------------------------------------------------------------------------
# Scheduler tools (via NotificationRule)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scoped_list_schedules_no_tenant_scope_ids() -> None:
    """Regression: the LLM-exposed list_schedules tool must not accept any tenant-scoping id."""
    from app.tools.scheduler_tools import make_scoped_list_schedules_tool

    scoped_tool = make_scoped_list_schedules_tool(membership_id=1)

    schema_fields = (
        scoped_tool.args_schema.model_fields if scoped_tool.args_schema else {}
    )
    tenant_ids = {"membership_id", "project_id", "user_id", "conversation_id"}
    leaked = tenant_ids & set(schema_fields)
    assert not leaked, f"Scoped tool must not expose tenant ids to LLM: {leaked}"
    assert scoped_tool.name == "list_schedules"


# ---------------------------------------------------------------------------
# Cross-project schedule isolation regression tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scoped_list_schedules_isolates_memberships(
    seeded_project: dict[str, Any],
) -> None:
    """Scoped list_schedules tool must only return schedules for its own membership.

    Regression test: the LLM must never see schedules from another project.
    """
    import app.tools.scheduler_tools as scheduler_tools_module
    from app.tools.scheduler_tools import make_scoped_list_schedules_tool

    old_factory = scheduler_tools_module.async_session_factory
    scheduler_tools_module.async_session_factory = _test_session_factory

    try:
        # -- Set up two projects with one membership each for the same user --
        project_a_id = seeded_project["project_id"]

        project_b_id = generate_project_id()
        async with _test_session_factory() as db:
            db.add(Project(id=project_b_id, display_name="Project B"))
            await db.flush()
            db.add(
                ProjectMembership(
                    project_id=project_b_id,
                    user_id="u_testuser_000000000000000000",
                    status="active",
                )
            )
            await db.commit()

        # Retrieve membership IDs
        async with _test_session_factory() as db:
            res_a = await db.execute(
                select(ProjectMembership).where(
                    ProjectMembership.project_id == project_a_id
                )
            )
            membership_a = res_a.scalar_one()
            res_b = await db.execute(
                select(ProjectMembership).where(
                    ProjectMembership.project_id == project_b_id
                )
            )
            membership_b = res_b.scalar_one()

        # Create one rule per membership directly in DB
        async with _test_session_factory() as db:
            db.add(
                NotificationRule(
                    membership_id=membership_a.id,
                    kind="daily_local_time",
                    config_json=json.dumps({"topic": "Morning Walk", "time": "08:00"}),
                    tz_policy="floating_user_tz",
                    is_active=True,
                )
            )
            db.add(
                NotificationRule(
                    membership_id=membership_b.id,
                    kind="daily_local_time",
                    config_json=json.dumps(
                        {"topic": "Evening Meditation", "time": "21:00"}
                    ),
                    tz_policy="floating_user_tz",
                    is_active=True,
                )
            )
            await db.commit()

        # Build scoped tool for membership A
        scoped_tool_a = make_scoped_list_schedules_tool(membership_a.id)

        # The scoped tool must NOT accept membership_id
        schema_fields = (
            scoped_tool_a.args_schema.model_fields if scoped_tool_a.args_schema else {}
        )
        assert "membership_id" not in schema_fields, (
            "Scoped tool must not expose membership_id to the LLM"
        )

        # Invoke with no arguments
        result = await scoped_tool_a.ainvoke({})

        # Must contain membership A's schedule
        assert "Morning Walk" in result
        assert "08:00" in result

        # Must NOT contain membership B's schedule
        assert "Evening Meditation" not in result
        assert "21:00" not in result

        # Verify tool name matches prompt expectations
        assert scoped_tool_a.name == "list_schedules"

    finally:
        scheduler_tools_module.async_session_factory = old_factory


@pytest.mark.asyncio
async def test_cross_project_delete_protection(
    seeded_project: dict[str, Any],
) -> None:
    """A delete proposal referencing a rule from another membership must be ignored.

    Regression test: a malicious or mistaken rule_id from project B must not
    deactivate the rule when processing proposals for membership A.
    """
    from app.agents.engine import _process_proposals
    from app.schemas.patches import UserProfileData
    from app.tools.proposal_tools import ProposalCollector

    # -- Set up two projects with one membership each --
    project_a_id = seeded_project["project_id"]

    project_b_id = generate_project_id()
    async with _test_session_factory() as db:
        db.add(Project(id=project_b_id, display_name="Project B"))
        await db.flush()
        db.add(
            ProjectMembership(
                project_id=project_b_id,
                user_id="u_testuser_000000000000000000",
                status="active",
            )
        )
        await db.commit()

    # Retrieve membership IDs
    async with _test_session_factory() as db:
        res_a = await db.execute(
            select(ProjectMembership).where(
                ProjectMembership.project_id == project_a_id
            )
        )
        membership_a = res_a.scalar_one()
        res_b = await db.execute(
            select(ProjectMembership).where(
                ProjectMembership.project_id == project_b_id
            )
        )
        membership_b = res_b.scalar_one()

    # Create a rule for membership B directly in DB
    async with _test_session_factory() as db:
        rule_b = NotificationRule(
            membership_id=membership_b.id,
            kind="daily_local_time",
            config_json=json.dumps({"topic": "Project B Nudge", "time": "07:00"}),
            tz_policy="floating_user_tz",
            is_active=True,
        )
        db.add(rule_b)
        await db.commit()
        rule_b_id = rule_b.id

    # Build a collector with a delete proposal targeting rule B,
    # but we'll process it under membership A's context.
    collector = ProposalCollector()
    collector.schedule_proposals.append(
        {
            "action": "delete",
            "rule_id": rule_b_id,
            "confidence": 0.9,
            "evidence": {"message_ids": [1], "quotes": ["remove that nudge"]},
            "source_bot": "COACH",
        }
    )

    profile = UserProfileData(
        prompt_anchor="test",
        preferred_time="08:00",
        habit_domain="exercise",
    )

    # Process proposals under membership A — must NOT delete B's rule
    async with _test_session_factory() as db:
        await _process_proposals(
            db=db,
            membership_id=membership_a.id,
            profile=profile,
            collector=collector,
            recent_message_ids=[1],
            latest_user_message_id=1,
        )

    # Verify membership B's rule is still active
    async with _test_session_factory() as db:
        rule_result = await db.execute(
            select(NotificationRule).where(
                NotificationRule.id == rule_b_id,
            )
        )
        rule_b_after = rule_result.scalar_one()
        assert rule_b_after.is_active is True, (
            "Rule from membership B must remain active when processed "
            "under membership A's context"
        )


@pytest.mark.asyncio
async def test_schedule_delete_cancels_pending_feedback_tasks(
    seeded_project: dict[str, Any],
) -> None:
    """Deleting a rule via proposal cancels pending scheduled feedback tasks."""
    from app.agents.engine import _process_proposals
    from app.schemas.patches import UserProfileData
    from app.tools.proposal_tools import ProposalCollector

    project_id = seeded_project["project_id"]
    async with _test_session_factory() as db:
        membership_result = await db.execute(
            select(ProjectMembership).where(ProjectMembership.project_id == project_id)
        )
        membership = membership_result.scalar_one()
        rule = NotificationRule(
            membership_id=membership.id,
            kind="daily_local_time",
            config_json=json.dumps({"topic": "Daily Nudge", "time": "08:00"}),
            tz_policy="floating_user_tz",
            is_active=True,
        )
        db.add(rule)
        await db.flush()
        task = ScheduledTask(
            membership_id=membership.id,
            rule_id=rule.id,
            task_type="feedback_request",
            payload_json='{"text":"How did this prompt work for you?"}',
            run_at_utc=datetime.now(UTC) + timedelta(hours=2),
            status="pending",
        )
        db.add(task)
        await db.commit()
        rule_id = rule.id
        task_id = task.id

    collector = ProposalCollector()
    collector.schedule_proposals.append(
        {
            "action": "delete",
            "rule_id": rule_id,
            "confidence": 0.9,
            "evidence": {"message_ids": [1], "quotes": ["remove the schedule"]},
            "source_bot": "COACH",
        }
    )

    async with _test_session_factory() as db:
        await _process_proposals(
            db=db,
            membership_id=membership.id,
            profile=UserProfileData(
                prompt_anchor="after coffee", preferred_time="08:00"
            ),
            collector=collector,
            recent_message_ids=[1],
            latest_user_message_id=1,
        )
        await db.commit()

    async with _test_session_factory() as db:
        rule_result = await db.execute(
            select(NotificationRule).where(NotificationRule.id == rule_id)
        )
        updated_rule = rule_result.scalar_one()
        task_result = await db.execute(
            select(ScheduledTask).where(ScheduledTask.id == task_id)
        )
        updated_task = task_result.scalar_one()
        assert updated_rule.is_active is False
        assert updated_task.status == "cancelled"
