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

from app.id_utils import generate_project_id
from app.models import (
    Base,
    OutboxEvent,
    PushSubscription,
    Project,
    ProjectInvite,
    ProjectMembership,
)

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


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Provide an httpx AsyncClient with overridden DB and auth."""
    # Import here to avoid module-level side effects
    from app.main import app
    from app.db import get_db
    from h4ckath0n.auth.dependencies import _get_current_user, require_admin

    # Create tables
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Override dependencies
    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[_get_current_user] = _override_require_user()
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
        json={"invite_code": invite_code, "email": "alice@example.com"},
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
        json={"invite_code": "wrong-code", "email": "alice@example.com"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_claim_invite_nonexistent_project(client: AsyncClient) -> None:
    resp = await client.post(
        "/p/p_nonexistent_00000000000000000/activate/claim",
        json={"invite_code": "any", "email": "alice@example.com"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_claim_invite_empty_email_returns_422(
    seeded_client: dict[str, Any],
) -> None:
    client = seeded_client["client"]
    project_id = seeded_client["project_id"]
    invite_code = seeded_client["invite_code"]

    resp = await client.post(
        f"/p/{project_id}/activate/claim",
        json={"invite_code": invite_code, "email": ""},
    )
    assert resp.status_code == 422
    errors = resp.json().get("detail", [])
    assert any(error.get("loc") == ["body", "email"] for error in errors)


@pytest.mark.asyncio
async def test_claim_invite_existing_membership_after_expiry_succeeds(
    seeded_client: dict[str, Any],
) -> None:
    client = seeded_client["client"]
    project_id = seeded_client["project_id"]
    invite_code = seeded_client["invite_code"]

    first = await client.post(
        f"/p/{project_id}/activate/claim",
        json={"invite_code": invite_code, "email": "existing@test.com"},
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
        json={"invite_code": invite_code, "email": "existing@test.com"},
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
        json={"invite_code": invite_code, "email": "ended@test.com"},
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
        json={"invite_code": invite_code, "email": "ended@test.com"},
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
        json={"invite_code": invite_code, "email": "alice@example.com"},
    )

    resp = await client.get("/dashboard")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["memberships"]) == 1
    assert data["memberships"][0]["project_id"] == project_id
    assert data["memberships"][0]["status"] == "active"


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
        json={"invite_code": invite_code, "email": "alice@example.com"},
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
async def test_push_subscribe(seeded_client: dict[str, Any]) -> None:
    client = seeded_client["client"]
    project_id = seeded_client["project_id"]
    invite_code = seeded_client["invite_code"]

    # Activate
    await client.post(
        f"/p/{project_id}/activate/claim",
        json={"invite_code": invite_code, "email": "alice@example.com"},
    )

    resp = await client.post(
        f"/p/{project_id}/push/subscribe",
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
async def test_push_subscribe_duplicate_updates(seeded_client: dict[str, Any]) -> None:
    """Re-subscribing with same endpoint updates keys instead of creating duplicate."""
    client = seeded_client["client"]
    project_id = seeded_client["project_id"]
    invite_code = seeded_client["invite_code"]

    await client.post(
        f"/p/{project_id}/activate/claim",
        json={"invite_code": invite_code, "email": "alice@example.com"},
    )

    endpoint = "https://push.example.com/sub/dedup"
    body = {
        "endpoint": endpoint,
        "keys": {"p256dh": "key1", "auth": "auth1"},
    }
    resp1 = await client.post(f"/p/{project_id}/push/subscribe", json=body)
    sub_id_1 = resp1.json()["subscription_id"]

    body["keys"] = {"p256dh": "key2", "auth": "auth2"}
    resp2 = await client.post(f"/p/{project_id}/push/subscribe", json=body)
    sub_id_2 = resp2.json()["subscription_id"]

    assert sub_id_1 == sub_id_2  # same subscription updated


@pytest.mark.asyncio
async def test_push_subscribe_same_endpoint_across_projects(
    seeded_client: dict[str, Any],
) -> None:
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
        json={"invite_code": first_invite_code, "email": "same-endpoint@test.com"},
    )
    await client.post(
        f"/p/{second_project_id}/activate/claim",
        json={"invite_code": second_invite_code, "email": "same-endpoint@test.com"},
    )

    endpoint = "https://push.example.com/sub/shared-endpoint"
    resp1 = await client.post(
        f"/p/{first_project_id}/push/subscribe",
        json={"endpoint": endpoint, "keys": {"p256dh": "key1", "auth": "auth1"}},
    )
    resp2 = await client.post(
        f"/p/{second_project_id}/push/subscribe",
        json={"endpoint": endpoint, "keys": {"p256dh": "key2", "auth": "auth2"}},
    )
    assert resp1.status_code == 200
    assert resp2.status_code == 200
    assert resp1.json()["subscription_id"] != resp2.json()["subscription_id"]

    async with _test_session_factory() as db:
        result = await db.execute(select(PushSubscription))
        rows = result.scalars().all()
        assert len(rows) == 2


@pytest.mark.asyncio
async def test_push_unsubscribe(seeded_client: dict[str, Any]) -> None:
    client = seeded_client["client"]
    project_id = seeded_client["project_id"]
    invite_code = seeded_client["invite_code"]

    await client.post(
        f"/p/{project_id}/activate/claim",
        json={"invite_code": invite_code, "email": "alice@example.com"},
    )

    endpoint = "https://push.example.com/sub/unsub"
    await client.post(
        f"/p/{project_id}/push/subscribe",
        json={
            "endpoint": endpoint,
            "keys": {"p256dh": "pk", "auth": "ak"},
        },
    )

    resp = await client.post(
        f"/p/{project_id}/push/unsubscribe",
        json={"endpoint": endpoint},
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


@pytest.mark.asyncio
async def test_push_unsubscribe_nonexistent(seeded_client: dict[str, Any]) -> None:
    client = seeded_client["client"]
    project_id = seeded_client["project_id"]
    invite_code = seeded_client["invite_code"]

    await client.post(
        f"/p/{project_id}/activate/claim",
        json={"invite_code": invite_code, "email": "alice@example.com"},
    )

    resp = await client.post(
        f"/p/{project_id}/push/unsubscribe",
        json={"endpoint": "https://push.example.com/does-not-exist"},
    )
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
        json={"invite_code": invite_code, "email": "me@test.com"},
    )

    resp = await client.get(f"/p/{project_id}/me")
    assert resp.status_code == 200
    data = resp.json()
    assert data["membership_status"] == "active"
    assert data["conversation_id"] is not None
    assert data["email"] == "me@test.com"


@pytest.mark.asyncio
async def test_profile_get_returns_defaults(seeded_client: dict[str, Any]) -> None:
    client = seeded_client["client"]
    project_id = seeded_client["project_id"]
    invite_code = seeded_client["invite_code"]

    await client.post(
        f"/p/{project_id}/activate/claim",
        json={"invite_code": invite_code, "email": "default@test.com"},
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
        json={"invite_code": invite_code, "email": "profile@test.com"},
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

    async with _test_session_factory() as db:
        outbox_result = await db.execute(
            select(OutboxEvent).where(OutboxEvent.project_id == project_id)
        )
        events = outbox_result.scalars().all()
        assert len(events) == 1
        first_available_at = events[0].available_at

    second_put_resp = await client.put(
        f"/p/{project_id}/profile",
        json={"prompt_anchor": "after dinner", "preferred_time": "19:30"},
    )
    assert second_put_resp.status_code == 200

    async with _test_session_factory() as db:
        outbox_result = await db.execute(
            select(OutboxEvent).where(OutboxEvent.project_id == project_id)
        )
        events = outbox_result.scalars().all()
        assert len(events) == 1
        assert events[0].available_at != first_available_at


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

    await client.post(
        f"/p/{project_id}/activate/claim",
        json={"invite_code": invite_code, "email": "admin-flow@test.com"},
    )
    await client.post(
        f"/p/{project_id}/push/subscribe",
        json={
            "endpoint": "https://push.example.com/sub/admin-export",
            "keys": {"p256dh": "pk", "auth": "ak"},
        },
    )
    await client.post(
        f"/p/{project_id}/messages",
        json={"text": "hello export"},
    )
    async with _test_session_factory() as db:
        membership_result = await db.execute(
            select(ProjectMembership).where(ProjectMembership.project_id == project_id)
        )
        membership = membership_result.scalar_one()
        db.add(
            OutboxEvent(
                project_id=project_id,
                membership_id=membership.id,
                type="scheduled_prompt",
                payload_json='{"project_id":"%s"}' % project_id,
                dedupe_key=f"scheduled_prompt:{membership.id}:2099-01-01",
                available_at=datetime.now(UTC),
            )
        )
        await db.commit()

    participants_after = await client.get(f"/admin/projects/{project_id}/participants")
    assert participants_after.status_code == 200
    participants = participants_after.json()["participants"]
    assert len(participants) == 1
    assert participants[0]["email"] == "admin-flow@test.com"
    assert "last_push_success_at" in participants[0]
    assert "last_push_failure_at" in participants[0]
    export_after = await client.get(f"/admin/projects/{project_id}/export")
    payload = export_after.json()
    assert isinstance(payload["messages"][0]["server_msg_id"], str)
    assert payload["messages"][0]["server_msg_id"] != ""
    assert "id" in payload["messages"][0]
    assert "client_msg_id" in payload["messages"][0]
    assert payload["push_subscriptions"][0]["membership_id"] is not None
    assert "dedupe_key" in payload["outbox_events"][0]
    assert "locked_until" in payload["outbox_events"][0]
    assert invite_code not in json.dumps(payload)


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
    first = await client.post(
        f"/p/{project_id}/activate/claim",
        json={"invite_code": invite_code, "email": "one@test.com"},
    )
    assert first.status_code == 200

    app.dependency_overrides[_get_current_user] = _override_require_user(
        "u_user_two_0000000000000000000"
    )
    second = await client.post(
        f"/p/{project_id}/activate/claim",
        json={"invite_code": invite_code, "email": "two@test.com"},
    )
    assert second.status_code == 200

    app.dependency_overrides[_get_current_user] = _override_require_user(
        "u_user_three_0000000000000000"
    )
    third = await client.post(
        f"/p/{project_id}/activate/claim",
        json={"invite_code": invite_code, "email": "three@test.com"},
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
        json={"invite_code": invite_code, "email": "repeat@test.com"},
    )
    assert first.status_code == 200
    second = await client.post(
        f"/p/{project_id}/activate/claim",
        json={"invite_code": invite_code, "email": "repeat@test.com"},
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
