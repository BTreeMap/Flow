"""Integration tests for the new architecture turn engine.

Tests the full pipeline: persist message → route → specialist → proposals → commit.
Uses an in-memory SQLite database with async SQLAlchemy.
"""

from __future__ import annotations

from typing import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import select

from app.models import (
    Base,
    Conversation,
    ConversationRuntimeState,
    Message,
    PatchAuditLog,
    Project,
    ProjectMembership,
    UserProfileStore,
)
from app.id_utils import generate_project_id, generate_server_msg_id
from app.agents.engine import _process_proposals, process_turn
from app.schemas.patches import UserProfileData
from app.services.profile_service import (
    load_user_profile,
    save_user_profile,
    load_memory_items,
    add_memory_item,
    log_patch_audit,
)
from app.schemas.patches import MemoryItemData
from app.tools.proposal_tools import ProposalCollector


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_engine = create_async_engine("sqlite+aiosqlite://", echo=False)
_session_factory = async_sessionmaker(_engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def db() -> AsyncGenerator[AsyncSession, None]:
    """Provide an async session with fresh tables."""
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with _session_factory() as session:
        yield session
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def seeded_db(db: AsyncSession) -> dict:
    """Seed a project, membership, and conversation."""
    project_id = generate_project_id()
    project = Project(id=project_id, display_name="Test Project")
    db.add(project)
    await db.flush()

    membership = ProjectMembership(
        project_id=project_id,
        user_id="u_testuser_000000000000000000",
        status="active",
    )
    db.add(membership)
    await db.flush()

    conv = Conversation(membership_id=membership.id)
    db.add(conv)
    await db.flush()

    await db.commit()
    await db.refresh(project)
    await db.refresh(membership)
    await db.refresh(conv)

    return {
        "db": db,
        "project_id": project_id,
        "membership_id": membership.id,
        "conversation": conv,
    }


# ---------------------------------------------------------------------------
# Profile persistence tests
# ---------------------------------------------------------------------------


class TestProfilePersistence:
    @pytest.mark.asyncio
    async def test_load_default_profile(self, db: AsyncSession) -> None:
        """Loading profile for non-existent membership returns defaults."""
        profile = await load_user_profile(db, membership_id=999)
        assert profile.prompt_anchor == ""
        assert profile.intensity == "normal"

    @pytest.mark.asyncio
    async def test_save_and_load_profile(self, seeded_db: dict) -> None:
        db = seeded_db["db"]
        mid = seeded_db["membership_id"]

        profile = UserProfileData(prompt_anchor="after coffee", preferred_time="8am")
        await save_user_profile(db, mid, profile)
        await db.commit()

        loaded = await load_user_profile(db, mid)
        assert loaded.prompt_anchor == "after coffee"
        assert loaded.preferred_time == "8am"

    @pytest.mark.asyncio
    async def test_save_updates_existing(self, seeded_db: dict) -> None:
        db = seeded_db["db"]
        mid = seeded_db["membership_id"]

        # Save initial
        await save_user_profile(db, mid, UserProfileData(prompt_anchor="v1"))
        await db.commit()

        # Update
        await save_user_profile(db, mid, UserProfileData(prompt_anchor="v2"))
        await db.commit()

        loaded = await load_user_profile(db, mid)
        assert loaded.prompt_anchor == "v2"

        # Should be only one row
        result = await db.execute(
            select(UserProfileStore).where(UserProfileStore.membership_id == mid)
        )
        assert len(result.scalars().all()) == 1


# ---------------------------------------------------------------------------
# Memory persistence tests
# ---------------------------------------------------------------------------


class TestMemoryPersistence:
    @pytest.mark.asyncio
    async def test_empty_memory(self, seeded_db: dict) -> None:
        db = seeded_db["db"]
        mid = seeded_db["membership_id"]
        items = await load_memory_items(db, mid)
        assert items == []

    @pytest.mark.asyncio
    async def test_add_and_load_memory(self, seeded_db: dict) -> None:
        db = seeded_db["db"]
        mid = seeded_db["membership_id"]

        item = MemoryItemData(
            content="User prefers mornings",
            source_message_ids=[1, 2],
            tags=["preference"],
        )
        await add_memory_item(db, mid, item)
        await db.commit()

        items = await load_memory_items(db, mid)
        assert len(items) == 1
        assert items[0].content == "User prefers mornings"
        assert items[0].source_message_ids == [1, 2]
        assert items[0].tags == ["preference"]


# ---------------------------------------------------------------------------
# Audit log tests
# ---------------------------------------------------------------------------


class TestAuditLog:
    @pytest.mark.asyncio
    async def test_audit_log_created(self, seeded_db: dict) -> None:
        db = seeded_db["db"]
        mid = seeded_db["membership_id"]

        await log_patch_audit(
            db=db,
            membership_id=mid,
            proposal_type="profile",
            source_bot="INTAKE",
            patch_json='{"prompt_anchor": "test"}',
            confidence=0.9,
            evidence_json='{"message_ids": [1]}',
            decision="committed",
        )
        await db.commit()

        result = await db.execute(
            select(PatchAuditLog).where(PatchAuditLog.membership_id == mid)
        )
        logs = result.scalars().all()
        assert len(logs) == 1
        assert logs[0].proposal_type == "profile"
        assert logs[0].source_bot == "INTAKE"
        assert logs[0].decision == "committed"

    @pytest.mark.asyncio
    async def test_ignored_patch_logged(self, seeded_db: dict) -> None:
        db = seeded_db["db"]
        mid = seeded_db["membership_id"]

        await log_patch_audit(
            db=db,
            membership_id=mid,
            proposal_type="profile",
            source_bot="COACH",
            patch_json='{"prompt_anchor": "test"}',
            confidence=0.3,
            evidence_json='{"message_ids": [1]}',
            decision="ignored: confidence too low",
        )
        await db.commit()

        result = await db.execute(
            select(PatchAuditLog).where(PatchAuditLog.membership_id == mid)
        )
        logs = result.scalars().all()
        assert len(logs) == 1
        assert "ignored" in logs[0].decision


# ---------------------------------------------------------------------------
# Engine turn pipeline (stub mode, no LLM)
# ---------------------------------------------------------------------------


class TestEngineTurnPipeline:
    @pytest.mark.asyncio
    async def test_turn_returns_assistant_text(self, seeded_db: dict) -> None:
        """Stub engine turn returns non-empty assistant text."""
        db = seeded_db["db"]
        conv = seeded_db["conversation"]
        mid = seeded_db["membership_id"]

        # Add a user message
        user_msg = Message(
            conversation_id=conv.id,
            role="user",
            content="Hello!",
            server_msg_id=generate_server_msg_id(),
        )
        db.add(user_msg)
        await db.flush()

        text, decision = await process_turn(
            db=db,
            conversation=conv,
            membership_id=mid,
            user_msg=user_msg,
            user_text="Hello!",
        )
        assert text  # non-empty
        assert decision.route in ("INTAKE", "FEEDBACK", "COACH")

    @pytest.mark.asyncio
    async def test_empty_profile_routes_to_intake(self, seeded_db: dict) -> None:
        """With empty profile, routes to INTAKE."""
        db = seeded_db["db"]
        conv = seeded_db["conversation"]
        mid = seeded_db["membership_id"]

        user_msg = Message(
            conversation_id=conv.id,
            role="user",
            content="Hi",
            server_msg_id=generate_server_msg_id(),
        )
        db.add(user_msg)
        await db.flush()

        _, decision = await process_turn(
            db=db,
            conversation=conv,
            membership_id=mid,
            user_msg=user_msg,
            user_text="Hi",
        )
        assert decision.route == "INTAKE"

    @pytest.mark.asyncio
    async def test_complete_profile_routes_to_coach(self, seeded_db: dict) -> None:
        """With complete profile, routes to COACH."""
        db = seeded_db["db"]
        conv = seeded_db["conversation"]
        mid = seeded_db["membership_id"]

        # Set up a complete profile
        profile = UserProfileData(
            prompt_anchor="after coffee",
            preferred_time="8am",
        )
        await save_user_profile(db, mid, profile)
        await db.flush()

        user_msg = Message(
            conversation_id=conv.id,
            role="user",
            content="How am I doing?",
            server_msg_id=generate_server_msg_id(),
        )
        db.add(user_msg)
        await db.flush()

        _, decision = await process_turn(
            db=db,
            conversation=conv,
            membership_id=mid,
            user_msg=user_msg,
            user_text="How am I doing?",
        )
        assert decision.route == "COACH"

    @pytest.mark.asyncio
    async def test_feedback_state_routes_correctly(self, seeded_db: dict) -> None:
        """With FEEDBACK state set, stub engine routes to FEEDBACK."""
        db = seeded_db["db"]
        conv = seeded_db["conversation"]
        mid = seeded_db["membership_id"]

        await save_user_profile(
            db,
            mid,
            UserProfileData(prompt_anchor="after coffee", preferred_time="8am"),
        )
        db.add(
            ConversationRuntimeState(
                conversation_id=conv.id,
                state_json='{"conversationState":"FEEDBACK"}',
            )
        )
        await db.flush()

        user_msg = Message(
            conversation_id=conv.id,
            role="user",
            content="I tried the habit today",
            server_msg_id=generate_server_msg_id(),
        )
        db.add(user_msg)
        await db.flush()

        _, decision = await process_turn(
            db=db,
            conversation=conv,
            membership_id=mid,
            user_msg=user_msg,
            user_text="I tried the habit today",
        )
        assert decision.route == "FEEDBACK"

    @pytest.mark.asyncio
    async def test_missing_evidence_message_ids_are_attached_for_feedback_profile_patch(
        self, seeded_db: dict
    ) -> None:
        db = seeded_db["db"]
        mid = seeded_db["membership_id"]
        conv = seeded_db["conversation"]

        user_msg = Message(
            conversation_id=conv.id,
            role="user",
            content="I struggled because evenings are hard",
            server_msg_id=generate_server_msg_id(),
        )
        db.add(user_msg)
        await db.flush()

        collector = ProposalCollector()
        collector.add_profile_proposal(
            {
                "patch": {"last_barrier": "evening fatigue"},
                "confidence": 0.9,
                "evidence": {"message_ids": [], "quotes": []},
                "source_bot": "FEEDBACK",
            }
        )

        profile = await load_user_profile(db, mid)
        updated = await _process_proposals(
            db,
            mid,
            profile,
            collector,
            recent_message_ids=[user_msg.id],
            latest_user_message_id=user_msg.id,
        )
        assert updated.last_barrier == "evening fatigue"
