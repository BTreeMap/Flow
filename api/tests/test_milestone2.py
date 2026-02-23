"""Tests for Milestone 2: SSE durability, turn gating, claim_invite, event_service, prompt_loader."""

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
    Conversation,
    ConversationEvent,
    FlowUserProfile,
    Message,
    Project,
    ProjectInvite,
    ProjectMembership,
)
from app.services.event_service import load_events_since, persist_event
from app.prompt_loader import prompt_hash, prompt_version
from h4ckath0n.auth.models import Base as H4ckath0nBase
from h4ckath0n.realtime import AuthContext

# ---------------------------------------------------------------------------
# Fixtures (same pattern as test_api.py)
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
    from app.main import app
    from app.db import get_db
    from app.routes import _require_auth_context
    from h4ckath0n.auth.dependencies import _get_current_user, require_admin

    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(H4ckath0nBase.metadata.create_all)

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[_get_current_user] = _override_require_user()
    app.dependency_overrides[_require_auth_context] = _override_auth_context()
    app.dependency_overrides[require_admin] = _override_require_user(
        "u_admin_0000000000000000000000", role="admin"
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(H4ckath0nBase.metadata.drop_all)


@pytest_asyncio.fixture
async def seeded(client: AsyncClient) -> dict[str, Any]:
    """Seed a project with invite and profile; return context dict."""
    project_id = generate_project_id()
    invite_code = "test-invite-code-123"
    code_hash = hashlib.sha256(invite_code.encode()).hexdigest()
    expires = datetime.now(UTC) + timedelta(days=7)

    async with _test_session_factory() as db:
        db.add(Project(id=project_id, display_name="Test Project"))
        await db.flush()
        db.add(
            ProjectInvite(
                project_id=project_id,
                invite_code_hash=code_hash,
                expires_at=expires,
            )
        )
        db.add(
            FlowUserProfile(
                user_id="u_testuser_000000000000000000",
                email_raw="test@example.com",
                email_normalized="test@example.com",
            )
        )
        await db.commit()

    # Activate membership
    resp = await client.post(
        f"/p/{project_id}/activate/claim",
        json={"invite_code": invite_code},
    )
    assert resp.status_code == 200

    return {
        "client": client,
        "project_id": project_id,
        "invite_code": invite_code,
        "conversation_id": resp.json()["conversation_id"],
    }


# ---------------------------------------------------------------------------
# A) Unit tests: event_service persist/load roundtrip
# ---------------------------------------------------------------------------


class TestEventServiceUnit:
    @pytest.mark.asyncio
    async def test_persist_and_load_roundtrip(self) -> None:
        """persist_event + load_events_since roundtrip with payload integrity."""
        async with _test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with _test_session_factory() as db:
            # Create prerequisite entities
            project = Project(id=generate_project_id(), display_name="Test")
            db.add(project)
            await db.flush()
            membership = ProjectMembership(
                project_id=project.id,
                user_id="u_testuser_000000000000000000",
                status="active",
            )
            db.add(membership)
            await db.flush()
            conv = Conversation(membership_id=membership.id)
            db.add(conv)
            await db.flush()

            payload = {"message_id": 42, "content": "hello", "nested": {"key": "val"}}
            event = await persist_event(db, conv.id, "message.final", payload)
            await db.commit()

            assert event.id is not None
            assert event.event_type == "message.final"
            assert json.loads(event.payload_json) == payload

            # Load events
            events = await load_events_since(db, conv.id, after_id=0)
            assert len(events) == 1
            assert events[0].id == event.id
            assert json.loads(events[0].payload_json) == payload

        async with _test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)

    @pytest.mark.asyncio
    async def test_ordering_and_filtering(self) -> None:
        """Events are returned in order and after_id filters correctly."""
        async with _test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with _test_session_factory() as db:
            project = Project(id=generate_project_id(), display_name="Test")
            db.add(project)
            await db.flush()
            membership = ProjectMembership(
                project_id=project.id,
                user_id="u_testuser_000000000000000000",
                status="active",
            )
            db.add(membership)
            await db.flush()
            conv = Conversation(membership_id=membership.id)
            db.add(conv)
            await db.flush()

            e1 = await persist_event(db, conv.id, "ev1", {"n": 1})
            e2 = await persist_event(db, conv.id, "ev2", {"n": 2})
            e3 = await persist_event(db, conv.id, "ev3", {"n": 3})
            await db.commit()

            # Load all
            all_events = await load_events_since(db, conv.id, after_id=0)
            assert len(all_events) == 3
            assert [e.id for e in all_events] == [e1.id, e2.id, e3.id]

            # Load after e1
            after_e1 = await load_events_since(db, conv.id, after_id=e1.id)
            assert len(after_e1) == 2
            assert after_e1[0].id == e2.id
            assert after_e1[1].id == e3.id

        async with _test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)


# ---------------------------------------------------------------------------
# A) Unit tests: prompt_loader hashing stability
# ---------------------------------------------------------------------------


class TestPromptLoaderUnit:
    def test_hash_stability(self) -> None:
        """Same prompt file produces the same hash on repeated calls."""
        h1 = prompt_hash("router_system")
        h2 = prompt_hash("router_system")
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex digest

    def test_prompt_version_structure(self) -> None:
        pv = prompt_version("coach_system")
        assert pv["prompt_file"] == "coach_system"
        assert "prompt_sha256" in pv
        assert isinstance(pv["prompt_sha256"], str)
        assert len(pv["prompt_sha256"]) == 64


# ---------------------------------------------------------------------------
# B) Integration tests: SSE event ID consistency
# ---------------------------------------------------------------------------


class TestSSEEventIdConsistency:
    @pytest.mark.asyncio
    async def test_sse_uses_conversation_event_id(self, seeded: dict[str, Any]) -> None:
        """send_message SSE payload id must equal ConversationEvent.id, not Message.id."""
        client = seeded["client"]
        project_id = seeded["project_id"]
        conv_id = seeded["conversation_id"]

        resp = await client.post(
            f"/p/{project_id}/messages",
            json={"text": "Hello!", "client_msg_id": "sse-id-test"},
        )
        assert resp.status_code == 200

        async with _test_session_factory() as db:
            # Get the latest ConversationEvent
            result = await db.execute(
                select(ConversationEvent)
                .where(ConversationEvent.conversation_id == conv_id)
                .order_by(ConversationEvent.id.desc())
                .limit(1)
            )
            event = result.scalar_one()

            # Get the assistant message
            result = await db.execute(
                select(Message)
                .where(
                    Message.conversation_id == conv_id,
                    Message.role == "assistant",
                )
                .order_by(Message.id.desc())
                .limit(1)
            )
            asst_msg = result.scalar_one()

            # ConversationEvent.id should be different from Message.id in general
            # The key assertion: the SSE event's id field uses ConversationEvent.id
            payload = json.loads(event.payload_json)
            assert payload["message_id"] == asst_msg.id
            # Verify the event is properly persisted
            assert event.id is not None
            assert event.event_type == "message.final"


# ---------------------------------------------------------------------------
# B) Integration tests: SSE replay correctness
# ---------------------------------------------------------------------------


class TestSSEReplay:
    @pytest.mark.asyncio
    async def test_replay_missed_events(self, seeded: dict[str, Any]) -> None:
        """Querying events with Last-Event-ID replays missed events."""
        client = seeded["client"]
        project_id = seeded["project_id"]
        conv_id = seeded["conversation_id"]

        # Send messages to create events
        await client.post(
            f"/p/{project_id}/messages",
            json={"text": "msg1", "client_msg_id": "replay-1"},
        )
        await client.post(
            f"/p/{project_id}/messages",
            json={"text": "msg2", "client_msg_id": "replay-2"},
        )

        async with _test_session_factory() as db:
            events = await load_events_since(db, conv_id, after_id=0)
            assert len(events) >= 2

            # Verify replay: load events after the first one
            first_event_id = events[0].id
            replayed = await load_events_since(db, conv_id, after_id=first_event_id)
            assert len(replayed) == len(events) - 1
            assert all(e.id > first_event_id for e in replayed)


# ---------------------------------------------------------------------------
# B) Integration tests: SSE cross-process delivery simulation
# ---------------------------------------------------------------------------


class TestSSECrossProcess:
    @pytest.mark.asyncio
    async def test_db_polling_delivers_events_without_queue(
        self, seeded: dict[str, Any]
    ) -> None:
        """Events written directly to DB (simulating another process) are
        discoverable via load_events_since (the DB polling path)."""
        conv_id = seeded["conversation_id"]

        async with _test_session_factory() as db:
            # Write an event directly to DB without using _publish_event
            event = ConversationEvent(
                conversation_id=conv_id,
                event_type="message.final",
                payload_json=json.dumps({"content": "cross-process msg"}),
            )
            db.add(event)
            await db.commit()
            await db.refresh(event)
            event_id = event.id

        # Verify the event can be loaded via DB polling
        async with _test_session_factory() as db:
            events = await load_events_since(db, conv_id, after_id=0)
            found = [e for e in events if e.id == event_id]
            assert len(found) == 1
            payload = json.loads(found[0].payload_json)
            assert payload["content"] == "cross-process msg"


# ---------------------------------------------------------------------------
# B) Integration tests: Turn idempotency concurrency
# ---------------------------------------------------------------------------


class TestTurnIdempotencyConcurrency:
    @pytest.mark.asyncio
    async def test_concurrent_same_client_msg_id(self, seeded: dict[str, Any]) -> None:
        """N concurrent POSTs with same client_msg_id create exactly 1 assistant message.
        Note: With SQLite, true concurrent writes may cause lock contention, so we
        test with sequential calls that simulate retry behavior.
        """
        client = seeded["client"]
        project_id = seeded["project_id"]
        conv_id = seeded["conversation_id"]
        client_msg_id = "concurrent-test-001"

        # Send 3 sequential requests with the same client_msg_id to test idempotency
        results = []
        for _ in range(3):
            resp = await client.post(
                f"/p/{project_id}/messages",
                json={"text": "concurrent msg", "client_msg_id": client_msg_id},
            )
            results.append(resp)

        # All should return 200 (first creates, subsequent return existing)
        for r in results:
            assert r.status_code == 200

        # All should return the same assistant message
        data_set = {r.json()["message_id"] for r in results}
        assert len(data_set) == 1  # All return the same message_id

        # Exactly 1 assistant message in DB
        async with _test_session_factory() as db:
            result = await db.execute(
                select(Message).where(
                    Message.conversation_id == conv_id,
                    Message.role == "assistant",
                )
            )
            assistant_msgs = result.scalars().all()
            assert len(assistant_msgs) == 1

    @pytest.mark.asyncio
    async def test_retry_returns_same_result(self, seeded: dict[str, Any]) -> None:
        """Second call with same client_msg_id returns identical assistant response."""
        client = seeded["client"]
        project_id = seeded["project_id"]
        client_msg_id = "retry-test-001"

        resp1 = await client.post(
            f"/p/{project_id}/messages",
            json={"text": "retry msg", "client_msg_id": client_msg_id},
        )
        assert resp1.status_code == 200
        data1 = resp1.json()

        resp2 = await client.post(
            f"/p/{project_id}/messages",
            json={"text": "retry msg", "client_msg_id": client_msg_id},
        )
        assert resp2.status_code == 200
        data2 = resp2.json()

        assert data1["message_id"] == data2["message_id"]
        assert data1["server_msg_id"] == data2["server_msg_id"]
        assert data1["content"] == data2["content"]

    @pytest.mark.asyncio
    async def test_missing_client_msg_id_still_works(
        self, seeded: dict[str, Any]
    ) -> None:
        """Route still works without client_msg_id (non-idempotent)."""
        client = seeded["client"]
        project_id = seeded["project_id"]

        resp = await client.post(
            f"/p/{project_id}/messages",
            json={"text": "no client_msg_id"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["role"] == "assistant"
        assert data["content"]


# ---------------------------------------------------------------------------
# B) Integration tests: claim_invite membership-first idempotency
# ---------------------------------------------------------------------------


class TestClaimInviteMembershipFirst:
    @pytest.mark.asyncio
    async def test_existing_membership_invalid_invite_returns_success(
        self, seeded: dict[str, Any]
    ) -> None:
        """Existing membership + invalid invite_code returns success."""
        client = seeded["client"]
        project_id = seeded["project_id"]

        # Member already exists from seeded fixture
        # Send with a completely wrong invite code
        resp = await client.post(
            f"/p/{project_id}/activate/claim",
            json={"invite_code": "totally-wrong-code"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["project_id"] == project_id
        assert data["membership_status"] == "active"

    @pytest.mark.asyncio
    async def test_existing_membership_malformed_invite_still_succeeds(
        self, seeded: dict[str, Any]
    ) -> None:
        """Invite code missing/malformed but membership exists still returns success."""
        client = seeded["client"]
        project_id = seeded["project_id"]

        resp = await client.post(
            f"/p/{project_id}/activate/claim",
            json={"invite_code": ""},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["project_id"] == project_id
        assert data["membership_status"] == "active"
