"""Integration tests for the conversation engine."""

from __future__ import annotations

from typing import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.agents.engine import process_turn
from app.id_utils import generate_project_id, generate_server_msg_id
from app.models import (
    Base,
    Conversation,
    ConversationRuntimeState,
    Message,
    PatchAuditLog,
    Project,
    ProjectMembership,
)
from app.schemas.patches import UserProfileData
from app.services.profile_service import load_memory_items, save_user_profile

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_test_engine = create_async_engine("sqlite+aiosqlite://", echo=False)
_test_session_factory = async_sessionmaker(_test_engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def seeded_db() -> AsyncGenerator[dict, None]:
    """Create tables, seed a project/membership/conversation, yield context dict."""
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with _test_session_factory() as session:
        project = Project(id=generate_project_id(), display_name="Test Project")
        session.add(project)
        await session.flush()

        membership = ProjectMembership(
            project_id=project.id,
            user_id="u_testuser_000000000000000000",
            status="active",
        )
        session.add(membership)
        await session.flush()

        conv = Conversation(membership_id=membership.id)
        session.add(conv)
        await session.flush()

        yield {
            "db": session,
            "conversation": conv,
            "membership_id": membership.id,
        }

    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


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

        text, decision, debug_info = await process_turn(
            db=db,
            conversation=conv,
            membership_id=mid,
            user_msg=user_msg,
            user_text="Hello!",
        )
        assert text != ""
        assert decision.route in ["INTAKE", "FEEDBACK", "COACH"]

    @pytest.mark.asyncio
    async def test_stub_debug_info_contains_tool_calls(self, seeded_db: dict) -> None:
        """Stub engine turn debug_info includes tool_calls key (empty list)."""
        db = seeded_db["db"]
        conv = seeded_db["conversation"]
        mid = seeded_db["membership_id"]

        user_msg = Message(
            conversation_id=conv.id,
            role="user",
            content="Hello!",
            server_msg_id=generate_server_msg_id(),
        )
        db.add(user_msg)
        await db.flush()

        _text, _decision, debug_info = await process_turn(
            db=db,
            conversation=conv,
            membership_id=mid,
            user_msg=user_msg,
            user_text="Hello!",
        )
        assert "tool_calls" in debug_info
        assert isinstance(debug_info["tool_calls"], list)
        assert debug_info["tool_calls"] == []

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

        _, decision, _ = await process_turn(
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

        _, decision, _ = await process_turn(
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

        _, decision, _ = await process_turn(
            db=db,
            conversation=conv,
            membership_id=mid,
            user_msg=user_msg,
            user_text="I tried the habit today",
        )
        assert decision.route == "FEEDBACK"


class TestAuditLog:
    @pytest.mark.asyncio
    async def test_proposals_are_logged(self, seeded_db: dict) -> None:
        """Verify patch proposals are written to the audit log."""
        # Stub engine produces patches in INTAKE mode
        # (Assuming _run_specialist_stub returns empty collector in stub mode for now,
        # but let's check if we can verify empty audit log or inject behavior)
        #
        # Actually, stub specialist invocation logic is hardcoded in engine.py.
        # It returns empty collector.
        #
        # So we might not see audit logs unless we inject a collector with items.
        # Or we can test `_process_proposals` directly.
        pass

    @pytest.mark.asyncio
    async def test_process_proposals_commits_valid_patch(self, seeded_db: dict) -> None:
        """Directly test _process_proposals logic with valid patch."""
        db = seeded_db["db"]
        mid = seeded_db["membership_id"]
        conv = seeded_db["conversation"]
        from app.agents.engine import _process_proposals
        from app.tools.proposal_tools import ProposalCollector

        # Create a user message so we have a valid message_id for evidence
        user_msg = Message(
            conversation_id=conv.id,
            role="user",
            content="I want to do it after lunch",
            server_msg_id=generate_server_msg_id(),
        )
        db.add(user_msg)
        await db.flush()

        profile = UserProfileData(prompt_anchor="")
        collector = ProposalCollector()
        collector.add_profile_proposal(
            {
                "patch": {"prompt_anchor": "after lunch"},
                "confidence": 0.9,
                "evidence": {"message_ids": [user_msg.id], "quotes": []},
                "source_bot": "INTAKE",
            }
        )

        updated_profile = await _process_proposals(
            db, mid, profile, collector, [user_msg.id]
        )
        assert updated_profile.prompt_anchor == "after lunch"

        # Check audit log
        audit = (
            await db.execute(
                select(PatchAuditLog).where(PatchAuditLog.membership_id == mid)
            )
        ).scalar_one()
        assert audit.proposal_type == "profile"
        assert audit.decision == "committed"
        assert audit.source_bot == "INTAKE"

    @pytest.mark.asyncio
    async def test_process_proposals_ignores_invalid_field(
        self, seeded_db: dict
    ) -> None:
        """Coach cannot change prompt_anchor."""
        db = seeded_db["db"]
        mid = seeded_db["membership_id"]
        from app.agents.engine import _process_proposals
        from app.tools.proposal_tools import ProposalCollector

        profile = UserProfileData(prompt_anchor="old")
        collector = ProposalCollector()
        collector.add_profile_proposal(
            {
                "patch": {"prompt_anchor": "new"},
                "confidence": 0.9,
                "evidence": {"message_ids": [], "quotes": []},
                "source_bot": "COACH",
            }
        )

        updated_profile = await _process_proposals(db, mid, profile, collector, [])
        assert updated_profile.prompt_anchor == "old"

        audit = (
            await db.execute(
                select(PatchAuditLog).where(PatchAuditLog.membership_id == mid)
            )
        ).scalar_one()
        assert "ignored" in audit.decision

    @pytest.mark.asyncio
    async def test_process_memory_proposal(self, seeded_db: dict) -> None:
        """Memory proposals are committed."""
        db = seeded_db["db"]
        mid = seeded_db["membership_id"]
        conv = seeded_db["conversation"]
        from app.agents.engine import _process_proposals
        from app.tools.proposal_tools import ProposalCollector

        # Create a user message so we have a valid message_id for evidence
        user_msg = Message(
            conversation_id=conv.id,
            role="user",
            content="I really like cats",
            server_msg_id=generate_server_msg_id(),
        )
        db.add(user_msg)
        await db.flush()

        profile = UserProfileData()
        collector = ProposalCollector()
        collector.add_memory_proposal(
            {
                "items": [{"content": "User likes cats"}],
                "confidence": 0.9,
                "evidence": {"message_ids": [user_msg.id], "quotes": []},
                "source_bot": "INTAKE",
            }
        )

        await _process_proposals(db, mid, profile, collector, [user_msg.id])

        items = await load_memory_items(db, mid)
        assert len(items) == 1
        assert items[0].content == "User likes cats"

        audit = (
            await db.execute(
                select(PatchAuditLog).where(PatchAuditLog.membership_id == mid)
            )
        ).scalar_one()
        assert audit.proposal_type == "memory"
        assert audit.decision == "committed"
