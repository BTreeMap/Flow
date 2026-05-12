"""API endpoint tests using httpx.AsyncClient + FastAPI TestClient."""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any, AsyncGenerator
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import clear_config_cache
from app.id_utils import generate_project_id
from app.models import (
    Base,
    Conversation,
    ConversationEvent,
    FlowUserProfile,
    Message,
    NotificationDelivery,
    Notification,
    ParticipantContact,
    PushSubscription,
    Project,
    ProjectInvite,
    ProjectMembership,
    ScheduledTask,
)
from h4ckath0n.auth.models import Base as H4ckath0nBase, Device
from h4ckath0n.realtime import AuthContext

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_test_engine = create_async_engine("sqlite+aiosqlite://", echo=False)
_test_session_factory = async_sessionmaker(_test_engine, expire_on_commit=False)


async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
    async with _test_session_factory() as session:
        yield session


def _make_fake_user(
    user_id: str = "u_testuser_000000000000000000",
    role: str = "user",
) -> MagicMock:
    user = MagicMock()
    user.id = user_id
    user.role = role
    user.email = "test@example.com"
    return user


def _override_require_user(
    user_id: str = "u_testuser_000000000000000000",
    role: str = "user",
) -> Any:
    """Return a dependency override that always provides a fake user."""
    fake = _make_fake_user(user_id, role=role)

    async def _dep() -> Any:
        return fake

    return _dep


def _override_auth_context(
    user_id: str = "u_testuser_000000000000000000",
    device_id: str = "d_testdevice_0000000000000000",
) -> Any:
    async def _dep() -> AuthContext:
        return AuthContext(user_id=user_id, device_id=device_id)

    return _dep


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Provide an httpx AsyncClient with overridden DB and auth."""
    # Import here to avoid module-level side effects
    from app.main import app
    from app.db import get_db
    from app.routes import _require_auth_context
    from h4ckath0n.auth.dependencies import _get_current_user, require_admin

    # Create tables
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(H4ckath0nBase.metadata.create_all)

    # Override dependencies
    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[_get_current_user] = _override_require_user()
    app.dependency_overrides[_require_auth_context] = _override_auth_context()
    app.dependency_overrides[require_admin] = _override_require_user(
        "u_admin_0000000000000000000000",
        role="admin",
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    # Cleanup
    app.dependency_overrides.clear()
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(H4ckath0nBase.metadata.drop_all)


@pytest_asyncio.fixture
async def seeded_client(client: AsyncClient) -> AsyncGenerator[dict[str, Any], None]:
    """Seed a project with invite and return context dict."""
    project_id = generate_project_id()
    invite_code = "test-invite-code-123"
    code_hash = hashlib.sha256(invite_code.encode()).hexdigest()
    expires = datetime.now(UTC) + timedelta(days=7)

    async with _test_session_factory() as db:
        project = Project(id=project_id, display_name="Test Project")
        db.add(project)
        await db.flush()

        invite = ProjectInvite(
            project_id=project_id,
            invite_code_hash=code_hash,
            expires_at=expires,
        )
        db.add(invite)
        db.add(
            FlowUserProfile(
                user_id="u_testuser_000000000000000000",
                email_raw="test@example.com",
                email_normalized="test@example.com",
            )
        )
        await db.commit()

    yield {
        "client": client,
        "project_id": project_id,
        "invite_code": invite_code,
    }


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_healthz(client: AsyncClient) -> None:
    resp = await client.get("/healthz")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["llm_mode"] in {"stub", "openai"}


@pytest.mark.asyncio
async def test_auth_me(client: AsyncClient) -> None:
    resp = await client.get("/auth/me")
    assert resp.status_code == 200
    assert resp.json()["user_id"] == "u_testuser_000000000000000000"


# ---------------------------------------------------------------------------
# Activation: claim invite (Scenario 1 precondition)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_claim_invite(seeded_client: dict[str, Any]) -> None:
    client = seeded_client["client"]
    project_id = seeded_client["project_id"]
    invite_code = seeded_client["invite_code"]

    resp = await client.post(
        f"/p/{project_id}/activate/claim",
        json={"invite_code": invite_code},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["project_id"] == project_id
    assert data["membership_status"] == "active"
    assert "conversation_id" in data


@pytest.mark.asyncio
async def test_claim_invite_invalid_code(seeded_client: dict[str, Any]) -> None:
    client = seeded_client["client"]
    project_id = seeded_client["project_id"]

    resp = await client.post(
        f"/p/{project_id}/activate/claim",
        json={"invite_code": "wrong-code"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_claim_invite_nonexistent_project(client: AsyncClient) -> None:
    resp = await client.post(
        "/p/p_nonexistent_00000000000000000/activate/claim",
        json={"invite_code": "any"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_claim_invite_existing_membership_after_expiry_succeeds(
    seeded_client: dict[str, Any],
) -> None:
    client = seeded_client["client"]
    project_id = seeded_client["project_id"]
    invite_code = seeded_client["invite_code"]

    first = await client.post(
        f"/p/{project_id}/activate/claim",
        json={"invite_code": invite_code},
    )
    assert first.status_code == 200

    async with _test_session_factory() as db:
        invite_result = await db.execute(
            select(ProjectInvite).where(ProjectInvite.project_id == project_id)
        )
        invite = invite_result.scalar_one()
        initial_uses = invite.uses
        invite.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        invite.revoked_at = datetime.now(UTC)
        await db.commit()

    second = await client.post(
        f"/p/{project_id}/activate/claim",
        json={"invite_code": invite_code},
    )
    assert second.status_code == 200

    async with _test_session_factory() as db:
        invite_result = await db.execute(
            select(ProjectInvite).where(ProjectInvite.project_id == project_id)
        )
        invite = invite_result.scalar_one()
        assert invite.uses == initial_uses


@pytest.mark.asyncio
async def test_claim_invite_existing_ended_membership_returns_403(
    seeded_client: dict[str, Any],
) -> None:
    client = seeded_client["client"]
    project_id = seeded_client["project_id"]
    invite_code = seeded_client["invite_code"]

    first = await client.post(
        f"/p/{project_id}/activate/claim",
        json={"invite_code": invite_code},
    )
    assert first.status_code == 200

    async with _test_session_factory() as db:
        membership_result = await db.execute(
            select(ProjectMembership).where(ProjectMembership.project_id == project_id)
        )
        membership = membership_result.scalar_one()
        membership.status = "ended"
        membership.ended_at = datetime.now(UTC)
        await db.commit()

    second = await client.post(
        f"/p/{project_id}/activate/claim",
        json={"invite_code": invite_code},
    )
    assert second.status_code == 403


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dashboard_empty(client: AsyncClient) -> None:
    resp = await client.get("/dashboard")
    assert resp.status_code == 200
    data = resp.json()
    assert data["memberships"] == []


@pytest.mark.asyncio
async def test_dashboard_after_activation(seeded_client: dict[str, Any]) -> None:
    client = seeded_client["client"]
    project_id = seeded_client["project_id"]
    invite_code = seeded_client["invite_code"]

    # Activate first
    await client.post(
        f"/p/{project_id}/activate/claim",
        json={"invite_code": invite_code},
    )

    resp = await client.get("/dashboard")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["memberships"]) == 1
    assert data["memberships"][0]["project_id"] == project_id
    assert data["memberships"][0]["status"] == "active"
    # New fields present (no messages yet)
    assert data["memberships"][0]["last_message_preview"] is None
    assert data["memberships"][0]["last_message_at"] is None


@pytest.mark.asyncio
async def test_dashboard_last_message(seeded_client: dict[str, Any]) -> None:
    client = seeded_client["client"]
    project_id = seeded_client["project_id"]
    invite_code = seeded_client["invite_code"]

    # Activate
    await client.post(
        f"/p/{project_id}/activate/claim",
        json={"invite_code": invite_code},
    )

    # Send a message so last_message_preview is populated
    await client.post(
        f"/p/{project_id}/messages",
        json={"text": "Hello preview!", "client_msg_id": "dash1"},
    )

    resp = await client.get("/dashboard")
    assert resp.status_code == 200
    data = resp.json()
    mem = data["memberships"][0]
    assert mem["last_message_preview"] is not None
    assert mem["last_message_at"] is not None


@pytest.mark.asyncio
async def test_dashboard_hides_feedback_action_last_message(
    seeded_client: dict[str, Any],
) -> None:
    client = seeded_client["client"]
    project_id = seeded_client["project_id"]
    invite_code = seeded_client["invite_code"]

    # Activate
    await client.post(
        f"/p/{project_id}/activate/claim",
        json={"invite_code": invite_code},
    )

    async with _test_session_factory() as db:
        membership_result = await db.execute(
            select(ProjectMembership).where(ProjectMembership.project_id == project_id)
        )
        membership = membership_result.scalar_one()
        conv_result = await db.execute(
            select(Conversation).where(Conversation.membership_id == membership.id)
        )
        conv = conv_result.scalar_one()

        db.add(
            Message(
                conversation_id=conv.id,
                role="assistant",
                content="Visible assistant message",
                server_msg_id="srv-visible-assistant-dashboard",
            )
        )
        db.add(
            Message(
                conversation_id=conv.id,
                role="user",
                content="[System: User provided feedback 'Needs tweaks' on notification 1]",
                server_msg_id="srv-feedback-hidden-dashboard",
                client_msg_id="feedback_action:1:fb_1",
            )
        )
        await db.commit()

    resp = await client.get("/dashboard")
    assert resp.status_code == 200
    data = resp.json()
    mem = data["memberships"][0]
    assert mem["last_message_preview"] == "Visible assistant message"


# ---------------------------------------------------------------------------
# Messaging
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_message(seeded_client: dict[str, Any]) -> None:
    client = seeded_client["client"]
    project_id = seeded_client["project_id"]
    invite_code = seeded_client["invite_code"]

    # Activate
    await client.post(
        f"/p/{project_id}/activate/claim",
        json={"invite_code": invite_code},
    )

    resp = await client.post(
        f"/p/{project_id}/messages",
        json={"text": "Hello, world!", "client_msg_id": "cmsg1"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["role"] == "assistant"
    assert data["content"]  # non-empty assistant response from engine
    assert data["server_msg_id"]

    list_resp = await client.get(f"/p/{project_id}/messages")
    assert list_resp.status_code == 200
    items = list_resp.json()["messages"]
    assert len(items) == 2
    assert items[0]["role"] == "user"
    assert items[1]["role"] == "assistant"


@pytest.mark.asyncio
async def test_send_message_cancels_pending_feedback_task(
    seeded_client: dict[str, Any],
) -> None:
    client = seeded_client["client"]
    project_id = seeded_client["project_id"]
    invite_code = seeded_client["invite_code"]

    await client.post(
        f"/p/{project_id}/activate/claim",
        json={"invite_code": invite_code},
    )

    async with _test_session_factory() as db:
        membership_result = await db.execute(
            select(ProjectMembership).where(ProjectMembership.project_id == project_id)
        )
        membership = membership_result.scalar_one()
        notification = Notification(
            membership_id=membership.id,
            title="Nudge",
            body="Do one small step now",
            payload_json="{}",
        )
        db.add(notification)
        await db.flush()

        task = ScheduledTask(
            membership_id=membership.id,
            parent_instance_id=notification.id,
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
            run_at_utc=datetime.now(UTC) + timedelta(hours=1),
            status="pending",
        )
        db.add(task)
        await db.commit()
        task_id = task.id
        notification_id = notification.id

    resp = await client.post(
        f"/p/{project_id}/messages",
        json={
            "text": "I already acted on it",
            "client_msg_id": "cancel-feedback-1",
            "current_notification_id": notification_id,
        },
    )
    assert resp.status_code == 200

    async with _test_session_factory() as db:
        task_result = await db.execute(
            select(ScheduledTask).where(ScheduledTask.id == task_id)
        )
        updated_task = task_result.scalar_one()
        assert updated_task.status == "cancelled"


@pytest.mark.asyncio
async def test_send_message_cancels_all_pending_feedback_tasks_for_membership(
    seeded_client: dict[str, Any],
) -> None:
    client = seeded_client["client"]
    project_id = seeded_client["project_id"]
    invite_code = seeded_client["invite_code"]

    await client.post(
        f"/p/{project_id}/activate/claim",
        json={"invite_code": invite_code},
    )

    async with _test_session_factory() as db:
        membership_result = await db.execute(
            select(ProjectMembership).where(ProjectMembership.project_id == project_id)
        )
        membership = membership_result.scalar_one()

        task_a = ScheduledTask(
            membership_id=membership.id,
            task_type="feedback_request",
            payload_json=json.dumps(
                {
                    "text": "A",
                    "actions": [
                        {"action": "fb_0", "title": "Works perfectly"},
                        {"action": "fb_1", "title": "Needs tweaks"},
                    ],
                }
            ),
            run_at_utc=datetime.now(UTC) + timedelta(hours=1),
            status="pending",
        )
        task_b = ScheduledTask(
            membership_id=membership.id,
            task_type="feedback_request",
            payload_json=json.dumps(
                {
                    "text": "B",
                    "actions": [
                        {"action": "fb_0", "title": "Works perfectly"},
                        {"action": "fb_1", "title": "Needs tweaks"},
                    ],
                }
            ),
            run_at_utc=datetime.now(UTC) + timedelta(hours=2),
            status="pending",
        )
        db.add(task_a)
        db.add(task_b)
        await db.commit()
        task_ids = [task_a.id, task_b.id]

    resp = await client.post(
        f"/p/{project_id}/messages",
        json={"text": "Just chatting", "client_msg_id": "cancel-feedback-all-1"},
    )
    assert resp.status_code == 200

    async with _test_session_factory() as db:
        result = await db.execute(
            select(ScheduledTask).where(ScheduledTask.id.in_(task_ids))
        )
        tasks = result.scalars().all()
        assert len(tasks) == 2
        assert all(task.status == "cancelled" for task in tasks)


@pytest.mark.asyncio
async def test_feedback_event_endpoint_creates_user_message(
    seeded_client: dict[str, Any],
) -> None:
    client = seeded_client["client"]
    project_id = seeded_client["project_id"]
    invite_code = seeded_client["invite_code"]

    await client.post(
        f"/p/{project_id}/activate/claim",
        json={"invite_code": invite_code},
    )

    async with _test_session_factory() as db:
        membership_result = await db.execute(
            select(ProjectMembership).where(ProjectMembership.project_id == project_id)
        )
        membership = membership_result.scalar_one()
        notification = Notification(
            membership_id=membership.id,
            title="Feedback Request",
            body="How did this prompt work for you?",
            payload_json="{}",
        )
        db.add(notification)
        await db.flush()
        delivery = NotificationDelivery(
            instance_id=notification.id,
            membership_id=membership.id,
            user_id="u_testuser_000000000000000000",
            channel="push_notify",
            payload_json=json.dumps(
                {
                    "actions": [
                        {"action": "fb_0", "title": "Works perfectly"},
                        {"action": "fb_1", "title": "Needs tweaks"},
                    ]
                }
            ),
            run_at_utc=datetime.now(UTC),
        )
        db.add(delivery)
        await db.commit()
        notification_id = notification.id
        membership_id = membership.id
        conv_result = await db.execute(
            select(Conversation).where(Conversation.membership_id == membership_id)
        )
        conv = conv_result.scalar_one()
        poll_message = Message(
            conversation_id=conv.id,
            role="assistant",
            content="How did this prompt work for you?",
            server_msg_id="srv-feedback-poll-message",
            client_msg_id="feedback:seeded",
            metadata_={
                "type": "feedback_poll",
                "notification_id": notification_id,
                "status": "pending",
                "actions": [
                    {"id": "fb_0", "title": "Works perfectly"},
                    {"id": "fb_1", "title": "Needs tweaks"},
                ],
            },
        )
        db.add(poll_message)
        await db.commit()

    resp = await client.post(
        f"/p/{project_id}/chat/events/feedback",
        json={
            "action_id": "fb_1",
            "notification_id": notification_id,
            "project_id": project_id,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"

    async with _test_session_factory() as db:
        msg_result = await db.execute(
            select(Message)
            .join(Conversation, Message.conversation_id == Conversation.id)
            .where(Conversation.membership_id == membership_id, Message.role == "user")
            .order_by(Message.id.desc())
        )
        message = msg_result.scalars().first()
        assert message is not None
        assert (
            message.content
            == f"[System: User provided feedback 'Needs tweaks' on notification {notification_id}]"
        )
        asst_result = await db.execute(
            select(Message)
            .join(Conversation, Message.conversation_id == Conversation.id)
            .where(
                Conversation.membership_id == membership_id,
                Message.role == "assistant",
            )
            .order_by(Message.id.desc())
        )
        asst_msg = asst_result.scalars().first()
        assert asst_msg is not None

        poll_result = await db.execute(
            select(Message)
            .join(Conversation, Message.conversation_id == Conversation.id)
            .where(
                Conversation.membership_id == membership_id,
                Message.client_msg_id == "feedback:seeded",
            )
        )
        poll_msg = poll_result.scalar_one()
        assert poll_msg.metadata_ is not None
        assert poll_msg.metadata_["status"] == "completed"
        assert poll_msg.metadata_["selected_action_id"] == "fb_1"

        event_result = await db.execute(
            select(ConversationEvent)
            .join(Conversation, ConversationEvent.conversation_id == Conversation.id)
            .where(
                Conversation.membership_id == membership_id,
                ConversationEvent.event_type == "message.final",
            )
            .order_by(ConversationEvent.id.desc())
        )
        event = event_result.scalars().first()
        assert event is not None
        updated_event_result = await db.execute(
            select(ConversationEvent)
            .join(Conversation, ConversationEvent.conversation_id == Conversation.id)
            .where(
                Conversation.membership_id == membership_id,
                ConversationEvent.event_type == "message.updated",
            )
            .order_by(ConversationEvent.id.desc())
        )
        updated_event = updated_event_result.scalars().first()
        assert updated_event is not None

    list_resp = await client.get(f"/p/{project_id}/messages")
    assert list_resp.status_code == 200
    visible = list_resp.json()["messages"]
    assert all(
        "[System: User provided feedback" not in item["content"] for item in visible
    )
    assert any(item["role"] == "assistant" for item in visible)


@pytest.mark.asyncio
async def test_list_messages_hides_feedback_action_messages(
    seeded_client: dict[str, Any],
) -> None:
    client = seeded_client["client"]
    project_id = seeded_client["project_id"]
    invite_code = seeded_client["invite_code"]

    await client.post(
        f"/p/{project_id}/activate/claim",
        json={"invite_code": invite_code},
    )

    async with _test_session_factory() as db:
        membership_result = await db.execute(
            select(ProjectMembership).where(ProjectMembership.project_id == project_id)
        )
        membership = membership_result.scalar_one()
        conv_result = await db.execute(
            select(Conversation).where(Conversation.membership_id == membership.id)
        )
        conv = conv_result.scalar_one()

        db.add(
            Message(
                conversation_id=conv.id,
                role="user",
                content="Visible user message",
                server_msg_id="srv-visible-user",
            )
        )
        db.add(
            Message(
                conversation_id=conv.id,
                role="assistant",
                content="Visible assistant message",
                server_msg_id="srv-visible-assistant",
            )
        )
        db.add(
            Message(
                conversation_id=conv.id,
                role="user",
                content="[System: User provided feedback 'Needs tweaks' on notification 1]",
                server_msg_id="srv-feedback-hidden",
                client_msg_id="feedback_action:1:fb_1",
            )
        )
        await db.commit()

    resp = await client.get(f"/p/{project_id}/messages")
    assert resp.status_code == 200
    messages = resp.json()["messages"]
    assert len(messages) == 2
    contents = [m["content"] for m in messages]
    assert "Visible user message" in contents
    assert "Visible assistant message" in contents


@pytest.mark.asyncio
async def test_send_message_no_membership(client: AsyncClient) -> None:
    resp = await client.post(
        "/p/p_nonexistent_00000000000000000/messages",
        json={"text": "hi"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Push subscription storage
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_webpush_subscribe(seeded_client: dict[str, Any]) -> None:
    client = seeded_client["client"]
    project_id = seeded_client["project_id"]
    invite_code = seeded_client["invite_code"]

    await client.post(
        f"/p/{project_id}/activate/claim",
        json={"invite_code": invite_code},
    )

    resp = await client.post(
        "/notifications/webpush/subscriptions",
        json={
            "endpoint": "https://push.example.com/sub/abc",
            "keys": {"p256dh": "test_p256dh_key", "auth": "test_auth_key"},
            "user_agent": "TestBrowser/1.0",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "subscription_id" in data


@pytest.mark.asyncio
async def test_webpush_subscribe_duplicate_updates(
    seeded_client: dict[str, Any],
) -> None:
    """Re-subscribing with same endpoint updates keys (user-scoped)."""
    client = seeded_client["client"]
    project_id = seeded_client["project_id"]
    invite_code = seeded_client["invite_code"]

    await client.post(
        f"/p/{project_id}/activate/claim",
        json={"invite_code": invite_code},
    )

    endpoint = "https://push.example.com/sub/dedup"
    body: dict[str, Any] = {
        "endpoint": endpoint,
        "keys": {"p256dh": "key1", "auth": "auth1"},
    }
    resp1 = await client.post("/notifications/webpush/subscriptions", json=body)
    sub_id_1 = resp1.json()["subscription_id"]

    body["keys"] = {"p256dh": "key2", "auth": "auth2"}
    resp2 = await client.post("/notifications/webpush/subscriptions", json=body)
    sub_id_2 = resp2.json()["subscription_id"]

    assert sub_id_1 == sub_id_2  # same subscription updated


@pytest.mark.asyncio
async def test_webpush_user_scoped_single_row(
    seeded_client: dict[str, Any],
) -> None:
    """User-scoped: subscribing creates ONE row regardless of membership count."""
    client = seeded_client["client"]
    first_project_id = seeded_client["project_id"]
    first_invite_code = seeded_client["invite_code"]

    second_project_id = generate_project_id()
    second_invite_code = "test-invite-code-456"
    code_hash = hashlib.sha256(second_invite_code.encode()).hexdigest()
    expires = datetime.now(UTC) + timedelta(days=7)
    async with _test_session_factory() as db:
        db.add(Project(id=second_project_id, display_name="Second Project"))
        db.add(
            ProjectInvite(
                project_id=second_project_id,
                invite_code_hash=code_hash,
                expires_at=expires,
            )
        )
        await db.commit()

    await client.post(
        f"/p/{first_project_id}/activate/claim",
        json={"invite_code": first_invite_code},
    )
    await client.post(
        f"/p/{second_project_id}/activate/claim",
        json={"invite_code": second_invite_code},
    )

    # User-scoped subscribe: creates ONE row
    endpoint = "https://push.example.com/sub/shared-endpoint"
    resp = await client.post(
        "/notifications/webpush/subscriptions",
        json={"endpoint": endpoint, "keys": {"p256dh": "key1", "auth": "auth1"}},
    )
    assert resp.status_code == 200

    async with _test_session_factory() as db:
        result = await db.execute(
            select(PushSubscription).where(PushSubscription.endpoint == endpoint)
        )
        rows = result.scalars().all()
        assert len(rows) == 1  # user-scoped: one row per user+endpoint


@pytest.mark.asyncio
async def test_webpush_unsubscribe(seeded_client: dict[str, Any]) -> None:
    client = seeded_client["client"]
    project_id = seeded_client["project_id"]
    invite_code = seeded_client["invite_code"]

    await client.post(
        f"/p/{project_id}/activate/claim",
        json={"invite_code": invite_code},
    )

    endpoint = "https://push.example.com/sub/unsub"
    resp = await client.post(
        "/notifications/webpush/subscriptions",
        json={
            "endpoint": endpoint,
            "keys": {"p256dh": "pk", "auth": "ak"},
        },
    )
    sub_id = resp.json()["subscription_id"]

    resp = await client.request(
        "DELETE", f"/notifications/webpush/subscriptions/{sub_id}"
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


@pytest.mark.asyncio
async def test_webpush_unsubscribe_nonexistent(
    seeded_client: dict[str, Any],
) -> None:
    client = seeded_client["client"]
    project_id = seeded_client["project_id"]
    invite_code = seeded_client["invite_code"]

    await client.post(
        f"/p/{project_id}/activate/claim",
        json={"invite_code": invite_code},
    )

    resp = await client.request("DELETE", "/notifications/webpush/subscriptions/99999")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Project /me endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_project_me(seeded_client: dict[str, Any]) -> None:
    client = seeded_client["client"]
    project_id = seeded_client["project_id"]
    invite_code = seeded_client["invite_code"]

    await client.post(
        f"/p/{project_id}/activate/claim",
        json={"invite_code": invite_code},
    )

    resp = await client.get(f"/p/{project_id}/me")
    assert resp.status_code == 200
    data = resp.json()
    assert data["membership_status"] == "active"
    assert data["conversation_id"] is not None
    assert data["email"] == "test@example.com"


@pytest.mark.asyncio
async def test_profile_get_returns_defaults(seeded_client: dict[str, Any]) -> None:
    client = seeded_client["client"]
    project_id = seeded_client["project_id"]
    invite_code = seeded_client["invite_code"]

    await client.post(
        f"/p/{project_id}/activate/claim",
        json={"invite_code": invite_code},
    )
    resp = await client.get(f"/p/{project_id}/profile")
    assert resp.status_code == 200
    profile = resp.json()
    assert profile["prompt_anchor"] == ""
    assert profile["preferred_time"] == ""


@pytest.mark.asyncio
async def test_profile_put_enables_non_intake_route(
    seeded_client: dict[str, Any],
) -> None:
    client = seeded_client["client"]
    project_id = seeded_client["project_id"]
    invite_code = seeded_client["invite_code"]

    await client.post(
        f"/p/{project_id}/activate/claim",
        json={"invite_code": invite_code},
    )
    put_resp = await client.put(
        f"/p/{project_id}/profile",
        json={"prompt_anchor": "after breakfast", "preferred_time": "08:00"},
    )
    assert put_resp.status_code == 200

    message_resp = await client.post(
        f"/p/{project_id}/messages",
        json={"text": "checking in"},
    )
    assert message_resp.status_code == 200
    assert (
        message_resp.json()["content"]
        == "I'm here to support your habit journey. How can I help you today?"
    )

    # Profile PUT no longer enqueues outbox events (outbox removed)

    second_put_resp = await client.put(
        f"/p/{project_id}/profile",
        json={"prompt_anchor": "after dinner", "preferred_time": "19:30"},
    )
    assert second_put_resp.status_code == 200


@pytest.mark.asyncio
async def test_admin_project_and_invite_endpoints(client: AsyncClient) -> None:
    from app.main import app
    from h4ckath0n.auth.dependencies import _get_current_user

    app.dependency_overrides[_get_current_user] = _override_require_user(
        "u_admin_0000000000000000000000", role="admin"
    )

    create_resp = await client.post(
        "/admin/projects",
        json={"display_name": "Study A"},
    )
    assert create_resp.status_code == 200
    project_id = create_resp.json()["project_id"]

    list_resp = await client.get("/admin/projects")
    assert list_resp.status_code == 200
    assert any(p["project_id"] == project_id for p in list_resp.json()["projects"])

    invite_resp = await client.post(
        f"/admin/projects/{project_id}/invites",
        json={
            "count": 1,
            "expires_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
            "max_uses": 2,
        },
    )
    assert invite_resp.status_code == 200
    invite_code = invite_resp.json()["invite_codes"][0]

    participants_resp = await client.get(f"/admin/projects/{project_id}/participants")
    assert participants_resp.status_code == 200
    assert participants_resp.json()["participants"] == []

    export_resp = await client.get(f"/admin/projects/{project_id}/export")
    assert export_resp.status_code == 200
    export_data = export_resp.json()
    assert export_data["project_id"] == project_id
    assert "memberships" in export_data
    assert "conversations" in export_data
    assert "messages" in export_data
    assert "push_subscriptions" in export_data
    assert "invite_codes" not in export_data

    async with _test_session_factory() as db:
        db.add(
            FlowUserProfile(
                user_id="u_admin_0000000000000000000000",
                email_raw="admin@example.com",
                email_normalized="admin@example.com",
            )
        )
        await db.commit()

    await client.post(
        f"/p/{project_id}/activate/claim",
        json={"invite_code": invite_code},
    )
    await client.post(
        "/notifications/webpush/subscriptions",
        json={
            "endpoint": "https://push.example.com/sub/admin-export",
            "keys": {"p256dh": "pk", "auth": "ak"},
        },
    )
    await client.post(
        f"/p/{project_id}/messages",
        json={"text": "hello export"},
    )
    participants_after = await client.get(f"/admin/projects/{project_id}/participants")
    assert participants_after.status_code == 200
    participants = participants_after.json()["participants"]
    assert len(participants) == 1
    assert participants[0]["email"] == "admin@example.com"
    assert "last_push_success_at" in participants[0]
    assert "last_push_failure_at" in participants[0]
    export_after = await client.get(f"/admin/projects/{project_id}/export")
    payload = export_after.json()
    assert isinstance(payload["messages"][0]["server_msg_id"], str)
    assert payload["messages"][0]["server_msg_id"] != ""
    assert "id" in payload["messages"][0]
    assert "client_msg_id" in payload["messages"][0]
    assert payload["push_subscriptions"][0]["user_id"] is not None
    assert invite_code not in json.dumps(payload)


@pytest.mark.asyncio
async def test_admin_debug_endpoints(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.main import app
    from h4ckath0n.auth.dependencies import _get_current_user

    app.dependency_overrides[_get_current_user] = _override_require_user(
        "u_admin_0000000000000000000000", role="admin"
    )

    monkeypatch.delenv("H4CKATH0N_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("VAPID_PUBLIC_KEY", "public")
    monkeypatch.delenv("VAPID_PRIVATE_KEY", raising=False)
    clear_config_cache()

    status_resp = await client.get("/admin/debug/status")
    assert status_resp.status_code == 200
    payload = status_resp.json()
    assert payload["llm_mode"] == "stub"
    assert payload["openai_api_key_configured"] is False
    assert payload["vapid_public_key_configured"] is True
    assert payload["vapid_private_key_configured"] is False
    assert "OpenAI API key missing: chat runs in stub mode" in payload["warnings"]
    assert "VAPID keys missing: push notifications disabled" in payload["warnings"]
    clear_config_cache()

    llm_resp = await client.post(
        "/admin/debug/llm-connectivity",
        json={"model": "gpt-4o-mini", "prompt": "test"},
    )
    assert llm_resp.status_code == 503


@pytest.mark.asyncio
async def test_admin_llm_connectivity_uses_model_and_h4ckath0n_key(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app import routes as routes_module
    from app.main import app
    from h4ckath0n.auth.dependencies import _get_current_user

    app.dependency_overrides[_get_current_user] = _override_require_user(
        "u_admin_0000000000000000000000", role="admin"
    )
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("H4CKATH0N_OPENAI_API_KEY", "h4-key")

    captured: dict[str, Any] = {}

    class _FakeResponse:
        content = "OK"

    class _FakeChatOpenAI:
        def __init__(self, **kwargs: Any) -> None:
            captured["kwargs"] = kwargs

        async def ainvoke(self, prompt: str) -> _FakeResponse:
            captured["prompt"] = prompt
            return _FakeResponse()

    monkeypatch.setattr(routes_module, "ChatOpenAI", _FakeChatOpenAI)

    resp = await client.post(
        "/admin/debug/llm-connectivity",
        json={"model": "gpt-4.1-mini", "prompt": "say ok"},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["ok"] is True
    assert payload["model"] == "gpt-4.1-mini"
    assert payload["response_text"] == "OK"
    assert captured["kwargs"]["api_key"] == "h4-key"
    assert captured["kwargs"]["model"] == "gpt-4.1-mini"
    assert captured["prompt"] == "say ok"


@pytest.mark.asyncio
async def test_auth_sessions_list_revoke_and_scope(client: AsyncClient) -> None:
    from app.main import app
    from app.routes import _require_auth_context
    from h4ckath0n.auth.dependencies import _get_current_user

    app.dependency_overrides[_get_current_user] = _override_require_user(
        "u_testuser_000000000000000000"
    )
    app.dependency_overrides[_require_auth_context] = _override_auth_context(
        "u_testuser_000000000000000000", "d_current"
    )

    async with _test_session_factory() as db:
        db.add(
            Device(
                id="d_current",
                user_id="u_testuser_000000000000000000",
                public_key_jwk="{}",
                label="Current Device",
            )
        )
        db.add(
            Device(
                id="d_other",
                user_id="u_testuser_000000000000000000",
                public_key_jwk="{}",
                label="Other Device",
            )
        )
        db.add(
            Device(
                id="d_foreign",
                user_id="u_other_user_000000000000000000",
                public_key_jwk="{}",
                label="Foreign",
            )
        )
        await db.commit()

    list_resp = await client.get("/auth/sessions")
    assert list_resp.status_code == 200
    sessions = list_resp.json()["sessions"]
    assert len(sessions) == 2
    assert any(s["device_id"] == "d_current" and s["is_current"] for s in sessions)

    revoke_own = await client.post("/auth/sessions/d_other/revoke")
    assert revoke_own.status_code == 200
    assert revoke_own.json()["ok"] is True

    revoke_foreign = await client.post("/auth/sessions/d_foreign/revoke")
    assert revoke_foreign.status_code == 404


@pytest.mark.asyncio
async def test_multi_use_invite_limit_enforced(client: AsyncClient) -> None:
    from app.main import app
    from h4ckath0n.auth.dependencies import _get_current_user

    app.dependency_overrides[_get_current_user] = _override_require_user(
        "u_admin_0000000000000000000000", role="admin"
    )
    create_resp = await client.post(
        "/admin/projects",
        json={"display_name": "Multi-use"},
    )
    project_id = create_resp.json()["project_id"]
    invite_resp = await client.post(
        f"/admin/projects/{project_id}/invites",
        json={
            "count": 1,
            "expires_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
            "max_uses": 2,
        },
    )
    invite_code = invite_resp.json()["invite_codes"][0]

    app.dependency_overrides[_get_current_user] = _override_require_user(
        "u_user_one_0000000000000000000"
    )
    async with _test_session_factory() as db:
        db.add(
            FlowUserProfile(
                user_id="u_user_one_0000000000000000000",
                email_raw="user1@example.com",
                email_normalized="user1@example.com",
            )
        )
        await db.commit()
    first = await client.post(
        f"/p/{project_id}/activate/claim",
        json={"invite_code": invite_code},
    )
    assert first.status_code == 200

    app.dependency_overrides[_get_current_user] = _override_require_user(
        "u_user_two_0000000000000000000"
    )
    async with _test_session_factory() as db:
        db.add(
            FlowUserProfile(
                user_id="u_user_two_0000000000000000000",
                email_raw="user2@example.com",
                email_normalized="user2@example.com",
            )
        )
        await db.commit()
    second = await client.post(
        f"/p/{project_id}/activate/claim",
        json={"invite_code": invite_code},
    )
    assert second.status_code == 200

    app.dependency_overrides[_get_current_user] = _override_require_user(
        "u_user_three_0000000000000000"
    )
    async with _test_session_factory() as db:
        db.add(
            FlowUserProfile(
                user_id="u_user_three_0000000000000000",
                email_raw="user3@example.com",
                email_normalized="user3@example.com",
            )
        )
        await db.commit()
    third = await client.post(
        f"/p/{project_id}/activate/claim",
        json={"invite_code": invite_code},
    )
    assert third.status_code == 400


@pytest.mark.asyncio
async def test_repeat_claim_same_user_does_not_increment_invite_use(
    seeded_client: dict[str, Any],
) -> None:
    client = seeded_client["client"]
    project_id = seeded_client["project_id"]
    invite_code = seeded_client["invite_code"]

    first = await client.post(
        f"/p/{project_id}/activate/claim",
        json={"invite_code": invite_code},
    )
    assert first.status_code == 200
    second = await client.post(
        f"/p/{project_id}/activate/claim",
        json={"invite_code": invite_code},
    )
    assert second.status_code == 200

    async with _test_session_factory() as db:
        invite_result = await db.execute(
            select(ProjectInvite).where(ProjectInvite.project_id == project_id)
        )
        invite = invite_result.scalar_one()
        memberships_result = await db.execute(
            select(ProjectMembership).where(ProjectMembership.project_id == project_id)
        )
        memberships = memberships_result.scalars().all()
        assert invite.uses == 1
        assert len(memberships) == 1


@pytest.mark.asyncio
async def test_invite_use_atomic_update_allows_single_consumer(
    seeded_client: dict[str, Any],
) -> None:
    project_id = seeded_client["project_id"]

    async with _test_session_factory() as db:
        result = await db.execute(
            select(ProjectInvite).where(ProjectInvite.project_id == project_id)
        )
        invite = result.scalar_one()
        invite.max_uses = 1
        invite.uses = 0
        await db.commit()

    async def _consume_once() -> int:
        async with _test_session_factory() as db:
            result = await db.execute(
                update(ProjectInvite)
                .where(
                    ProjectInvite.project_id == project_id,
                    or_(
                        ProjectInvite.max_uses.is_(None),
                        ProjectInvite.uses < ProjectInvite.max_uses,
                    ),
                )
                .values(uses=ProjectInvite.uses + 1)
                .execution_options(synchronize_session=False)
            )
            await db.commit()
            return int(result.rowcount or 0)

    first, second = await asyncio.gather(_consume_once(), _consume_once())
    assert first + second == 1


# ---------------------------------------------------------------------------
# GET /me and PATCH /me
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_me(client: AsyncClient) -> None:
    resp = await client.get("/me")
    assert resp.status_code == 200
    data = resp.json()
    assert data["user_id"] == "u_testuser_000000000000000000"
    assert "email" in data
    assert "display_name" in data
    assert "is_admin" in data


@pytest.mark.asyncio
async def test_patch_me_display_name(client: AsyncClient) -> None:
    resp = await client.patch("/me", json={"display_name": "Alice"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["display_name"] == "Alice"

    # Verify persistence
    resp2 = await client.get("/me")
    assert resp2.json()["display_name"] == "Alice"


@pytest.mark.asyncio
async def test_patch_me_email(client: AsyncClient) -> None:
    resp = await client.patch("/me", json={"email": "new@example.com"})
    assert resp.status_code == 200
    assert resp.json()["email"] == "new@example.com"

    resp2 = await client.get("/me")
    assert resp2.status_code == 200
    assert resp2.json()["email"] == "new@example.com"

    async with _test_session_factory() as db:
        profile_result = await db.execute(
            select(FlowUserProfile).where(
                FlowUserProfile.user_id == "u_testuser_000000000000000000"
            )
        )
        profile = profile_result.scalar_one()
        assert profile.email_raw == "new@example.com"
        assert profile.email_normalized == "new@example.com"


# ---------------------------------------------------------------------------
# Claim invite without email returns 409
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_claim_invite_without_email_returns_409(
    seeded_client: dict[str, Any],
) -> None:
    """Claim invite without Flow profile email returns EMAIL_REQUIRED."""

    client = seeded_client["client"]
    project_id = seeded_client["project_id"]
    invite_code = seeded_client["invite_code"]
    user_id = "u_testuser_000000000000000000"

    async with _test_session_factory() as db:
        profile_result = await db.execute(
            select(FlowUserProfile).where(FlowUserProfile.user_id == user_id)
        )
        profile = profile_result.scalar_one()
        profile.email_raw = None
        profile.email_normalized = None
        await db.commit()

    resp = await client.post(
        f"/p/{project_id}/activate/claim",
        json={"invite_code": invite_code},
    )
    assert resp.status_code == 409
    data = resp.json()
    assert data["code"] == "EMAIL_REQUIRED"

    patch_resp = await client.patch("/me", json={"email": "retry@example.com"})
    assert patch_resp.status_code == 200

    retry_resp = await client.post(
        f"/p/{project_id}/activate/claim",
        json={"invite_code": invite_code},
    )
    assert retry_resp.status_code == 200

    project_me_resp = await client.get(f"/p/{project_id}/me")
    assert project_me_resp.status_code == 200
    assert project_me_resp.json()["email"] == "retry@example.com"

    async with _test_session_factory() as db:
        membership_result = await db.execute(
            select(ProjectMembership).where(
                ProjectMembership.project_id == project_id,
                ProjectMembership.user_id == user_id,
            )
        )
        membership = membership_result.scalar_one()
        contact_result = await db.execute(
            select(ParticipantContact)
            .where(ParticipantContact.membership_id == membership.id)
            .order_by(ParticipantContact.created_at.desc())
            .limit(1)
        )
        contact = contact_result.scalar_one()
        assert contact.email_raw == "retry@example.com"


# ---------------------------------------------------------------------------
# Invite concurrency: IntegrityError path must not consume invite uses
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_claim_invite_integrity_error_does_not_consume_uses(
    seeded_client: dict[str, Any],
) -> None:
    """Regression test: if membership already exists on IntegrityError path,
    invite uses must NOT be incremented."""
    client = seeded_client["client"]
    project_id = seeded_client["project_id"]
    invite_code = seeded_client["invite_code"]

    # First claim creates the membership and consumes one invite use.
    first = await client.post(
        f"/p/{project_id}/activate/claim",
        json={"invite_code": invite_code},
    )
    assert first.status_code == 200

    async with _test_session_factory() as db:
        invite_result = await db.execute(
            select(ProjectInvite).where(ProjectInvite.project_id == project_id)
        )
        invite = invite_result.scalar_one()
        uses_after_first = invite.uses

    # Second claim by the same user hits the existing-membership path.
    # Invite uses must remain unchanged.
    second = await client.post(
        f"/p/{project_id}/activate/claim",
        json={"invite_code": invite_code},
    )
    assert second.status_code == 200

    async with _test_session_factory() as db:
        invite_result = await db.execute(
            select(ProjectInvite).where(ProjectInvite.project_id == project_id)
        )
        invite = invite_result.scalar_one()
        assert invite.uses == uses_after_first, (
            "IntegrityError/existing-membership path must not consume invite uses"
        )
