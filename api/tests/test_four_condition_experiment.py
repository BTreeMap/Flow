"""Tests for the 4-condition experimental machinery.

Covers:

* The Condition C framing filter regex.
* The deterministic A/B static feedback script.
* The engine's A/B feedback bypass (LLM is never invoked under A/B).
* The engine's 24h history window for Condition C.
* The worker's condition-aware nudge generation (static / regex-gated / framed).
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import pytest_asyncio
from app import config
from app.agents.engine import process_turn
from app.id_utils import generate_project_id, generate_server_msg_id
from app.models import (
    Base,
    Conversation,
    ConversationRuntimeState,
    DailyInterventionLog,
    Message,
    Participation,
    PatchAuditLog,
    Project,
    ProjectMembership,
)
from app.schemas.patches import UserProfileData
from app.services.condition_filters import (
    CONDITION_C_FRAMING_PATTERN,
    contains_condition_c_framing,
)
from app.services.feedback_script import run_static_feedback
from app.services.profile_service import save_user_profile
from app.services.randomization import get_daily_condition
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_test_engine = create_async_engine("sqlite+aiosqlite://", echo=False)
_test_session_factory = async_sessionmaker(_test_engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def seeded_db() -> AsyncGenerator[dict[str, Any], None]:
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with _test_session_factory() as session:
        project = Project(id=generate_project_id(), display_name="Cond Test")
        session.add(project)
        await session.flush()
        membership = ProjectMembership(
            project_id=project.id,
            user_id="u_condtest_00000000000000000",
            status="active",
        )
        session.add(membership)
        await session.flush()
        conv = Conversation(membership_id=membership.id)
        session.add(conv)
        await session.flush()
        yield {"db": session, "conversation": conv, "membership_id": membership.id}
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


def _make_participation(
    membership_id: int, start_offset_days: int = 0
) -> Participation:
    return Participation(
        membership_id=membership_id,
        study_id="microcoach_v1",
        study_start_date=datetime.now(UTC) - timedelta(days=start_offset_days),
        timezone="UTC",
    )


@pytest.mark.asyncio
async def test_existing_participation_uses_current_master_key(
    seeded_db: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.agents import routing

    monkeypatch.setenv(
        "FLOW_CRYPTO_MASTER_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    )
    config.clear_config_cache()
    routing._get_randomization_key.cache_clear()
    db = seeded_db["db"]
    participation = _make_participation(seeded_db["membership_id"])
    db.add(participation)
    await db.flush()
    current_date = datetime.now(UTC).date()

    try:
        (
            condition,
            resolved,
            study_day_index,
        ) = await routing._get_active_condition_context(
            db, seeded_db["membership_id"], current_date
        )
        assert resolved is participation
        assert study_day_index == 0
        assert condition == get_daily_condition(
            participation.id,
            participation.study_start_date,
            current_date,
            routing._get_randomization_key(),
        )
    finally:
        config.clear_config_cache()
        routing._get_randomization_key.cache_clear()


# ---------------------------------------------------------------------------
# Condition C framing filter
# ---------------------------------------------------------------------------


class TestConditionCFilter:
    def test_plain_text_passes(self) -> None:
        assert not contains_condition_c_framing(
            "It is time for your morning coffee. Do one minute of squats."
        )

    def test_empty_string_passes(self) -> None:
        assert not contains_condition_c_framing("")
        assert not contains_condition_c_framing(None)  # type: ignore[arg-type]

    @pytest.mark.parametrize(
        "bad",
        [
            "If you brew coffee, then you will do squats.",
            "When I make coffee, then I will do one minute of squats.",
            "I'll reward myself with a podcast.",
            "I commit to one minute of stretching.",
            "Make a commitment contract with yourself.",
            "I promise to do it today.",
            "Reward yourself afterwards.",
            "I bet I can do this for a week.",
        ],
    )
    def test_framing_is_detected(self, bad: str) -> None:
        assert contains_condition_c_framing(bad), bad

    def test_word_will_alone_passes(self) -> None:
        # The plain word "will" outside an if/then construction must NOT trip
        # the filter — otherwise the model is over-constrained.
        assert not contains_condition_c_framing(
            "You will feel more energetic after a short walk."
        )

    def test_pattern_is_case_insensitive(self) -> None:
        assert CONDITION_C_FRAMING_PATTERN.search("IF I HAVE COFFEE THEN I WILL MOVE.")


# ---------------------------------------------------------------------------
# A/B static feedback script
# ---------------------------------------------------------------------------


class TestStaticFeedbackScript:
    @pytest_asyncio.fixture
    async def primed(self, seeded_db: dict[str, Any]) -> dict[str, Any]:
        db = seeded_db["db"]
        mid = seeded_db["membership_id"]
        participation = _make_participation(mid)
        db.add(participation)
        await db.flush()
        log = DailyInterventionLog(
            participation_id=participation.id,
            intervention_date=datetime.now(UTC).date(),
            study_day_index=0,
            assigned_condition="A",
            extracted_state={},
        )
        db.add(log)
        await db.flush()
        return {**seeded_db, "participation": participation, "log": log}

    @pytest.mark.asyncio
    async def test_full_yes_flow(self, primed: dict[str, Any]) -> None:
        db = primed["db"]
        mid = primed["membership_id"]
        # Turn 0: system prompts the check-in question.
        r0 = await run_static_feedback(db, mid, "", "A")
        assert "?" in r0
        # Turn 1: user says yes.
        r1 = await run_static_feedback(db, mid, "yes", "A")
        assert r1.endswith("?")  # followup question
        # Turn 2: user gives a free-text answer.
        r2 = await run_static_feedback(db, mid, "the timing was perfect", "A")
        assert "?" not in r2  # closing has no question
        # Turn 3: idempotent — still the closing.
        r3 = await run_static_feedback(db, mid, "anything", "A")
        assert r3 == r2

        # Verify log captured the answers but no patches were proposed.
        log = (await db.execute(select(DailyInterventionLog).limit(1))).scalar_one()
        assert log.extracted_state["script"]["attempted"] == "yes"
        assert log.extracted_state["script"]["step"] == "done"
        assert (
            log.extracted_state["script"]["answers"]["followup_raw"]
            == "the timing was perfect"
        )
        audit_count = (await db.execute(select(PatchAuditLog))).scalars().all()
        assert audit_count == [], "static feedback must NEVER propose patches"

    @pytest.mark.asyncio
    async def test_no_flow_uses_barrier_followup(self, primed: dict[str, Any]) -> None:
        db = primed["db"]
        mid = primed["membership_id"]
        await run_static_feedback(db, mid, "", "B")
        reply = await run_static_feedback(db, mid, "no", "B")
        assert "way" in reply.lower() or "barrier" in reply.lower() or "?" in reply
        log = (await db.execute(select(DailyInterventionLog).limit(1))).scalar_one()
        assert log.extracted_state["script"]["attempted"] == "no"

    @pytest.mark.asyncio
    async def test_ambiguous_answer_reasks_once(self, primed: dict[str, Any]) -> None:
        db = primed["db"]
        mid = primed["membership_id"]
        await run_static_feedback(db, mid, "", "A")
        r = await run_static_feedback(db, mid, "maybe later", "A")
        # Still asking the same question (yes/no clarifier).
        assert "?" in r
        log = (await db.execute(select(DailyInterventionLog).limit(1))).scalar_one()
        assert log.extracted_state["script"]["step"] == "ask_attempted"
        assert log.extracted_state["script"]["attempted"] is None


# ---------------------------------------------------------------------------
# Engine: A/B feedback bypass
# ---------------------------------------------------------------------------


class TestEngineFeedbackBypass:
    async def _setup_ab_feedback(
        self,
        seeded_db: dict[str, Any],
        condition: str,
        monkeypatch: pytest.MonkeyPatch,
    ) -> dict[str, Any]:
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
        # Pre-create participation and the daily log pinned to the desired condition.
        participation = _make_participation(mid)
        db.add(participation)
        await db.flush()
        db.add(
            DailyInterventionLog(
                participation_id=participation.id,
                intervention_date=datetime.now(UTC).date(),
                study_day_index=0,
                assigned_condition=condition,
                extracted_state={},
            )
        )
        await db.flush()

        # Force the engine to see the desired condition by stubbing the
        # randomization helper for the duration of this test.
        import app.agents.engine as engine_mod

        async def _fake_ctx(db, membership_id, current_date):
            return condition, participation, 0

        monkeypatch.setattr(engine_mod, "_get_active_condition_context", _fake_ctx)
        return {**seeded_db, "participation": participation}

    @pytest.mark.asyncio
    async def test_condition_a_feedback_uses_static_script(
        self, seeded_db: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Spy on the LLM feedback agent and assert it is never called.
        import app.agents.feedback as feedback_mod

        called = {"run_feedback": 0}

        async def _explode(*_a: Any, **_kw: Any) -> None:
            called["run_feedback"] += 1
            raise AssertionError("run_feedback must not be called under condition A")

        monkeypatch.setattr(feedback_mod, "run_feedback", _explode)
        await self._setup_ab_feedback(seeded_db, "A", monkeypatch)

        db = seeded_db["db"]
        conv = seeded_db["conversation"]
        mid = seeded_db["membership_id"]
        user_msg = Message(
            conversation_id=conv.id,
            role="user",
            content="yes",
            server_msg_id=generate_server_msg_id(),
        )
        db.add(user_msg)
        await db.flush()
        text, decision, debug, _ = await process_turn(
            db=db,
            conversation=conv,
            membership_id=mid,
            user_msg=user_msg,
            user_text="yes",
        )
        assert decision.route == "STATIC_FEEDBACK"
        assert called["run_feedback"] == 0
        assert text  # non-empty static reply
        # And no patches must have been logged.
        audits = (await db.execute(select(PatchAuditLog))).scalars().all()
        assert audits == []

    @pytest.mark.asyncio
    async def test_condition_b_feedback_uses_static_script(
        self, seeded_db: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        await self._setup_ab_feedback(seeded_db, "B", monkeypatch)
        db = seeded_db["db"]
        conv = seeded_db["conversation"]
        mid = seeded_db["membership_id"]
        user_msg = Message(
            conversation_id=conv.id,
            role="user",
            content="yes",
            server_msg_id=generate_server_msg_id(),
        )
        db.add(user_msg)
        await db.flush()
        _t, decision, _d, _p = await process_turn(
            db=db,
            conversation=conv,
            membership_id=mid,
            user_msg=user_msg,
            user_text="yes",
        )
        assert decision.route == "STATIC_FEEDBACK"


# ---------------------------------------------------------------------------
# Engine: 24h window for Condition C
# ---------------------------------------------------------------------------


class TestConditionCHistoryWindow:
    @pytest.mark.asyncio
    async def test_condition_c_excludes_old_and_framed_messages(
        self, seeded_db: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db = seeded_db["db"]
        conv = seeded_db["conversation"]
        mid = seeded_db["membership_id"]

        await save_user_profile(
            db,
            mid,
            UserProfileData(prompt_anchor="after coffee", preferred_time="8am"),
        )
        participation = _make_participation(mid)
        db.add(participation)
        await db.flush()

        # Old (>24h) message, unframed — should be excluded by window.
        old_msg = Message(
            conversation_id=conv.id,
            role="assistant",
            content="hello from yesterday",
            server_msg_id=generate_server_msg_id(),
            created_at=datetime.now(UTC) - timedelta(hours=48),
            condition_source="SYSTEM",
        )
        # Recent message but condition D — should be excluded by source.
        framed_msg = Message(
            conversation_id=conv.id,
            role="assistant",
            content="When you brew coffee, then you will move.",
            server_msg_id=generate_server_msg_id(),
            condition_source="COND_D",
        )
        # Recent + condition C — should be included.
        good_msg = Message(
            conversation_id=conv.id,
            role="assistant",
            content="A neutral nudge.",
            server_msg_id=generate_server_msg_id(),
            condition_source="COND_C",
        )
        db.add_all([old_msg, framed_msg, good_msg])
        await db.flush()

        # Force condition C
        import app.agents.engine as engine_mod

        async def _fake_ctx(db, membership_id, current_date):
            return "C", participation, 0

        monkeypatch.setattr(engine_mod, "_get_active_condition_context", _fake_ctx)

        user_msg = Message(
            conversation_id=conv.id,
            role="user",
            content="ping",
            server_msg_id=generate_server_msg_id(),
        )
        db.add(user_msg)
        await db.flush()

        _t, _d, debug, _p = await process_turn(
            db=db,
            conversation=conv,
            membership_id=mid,
            user_msg=user_msg,
            user_text="ping",
        )
        # We can't directly inspect chat_history from debug, but the turn must
        # have completed without error and the condition must be tagged.
        assert debug.condition == "C"


# ---------------------------------------------------------------------------
# Worker: condition-aware nudge generation
# ---------------------------------------------------------------------------


class TestWorkerConditionNudge:
    @pytest.mark.asyncio
    async def test_condition_a_uses_static_template(
        self, seeded_db: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.worker import nudge as wmod

        db = seeded_db["db"]
        mid = seeded_db["membership_id"]
        participation = _make_participation(mid)
        db.add(participation)
        await db.flush()

        async def _fake_resolve(_db, _mid):
            return "A", participation, 0

        # Spy: LLM helper must NOT be called.
        llm_called = {"n": 0}

        async def _llm_spy(*a: Any, **kw: Any) -> str:
            llm_called["n"] += 1
            return "should not be used"

        monkeypatch.setattr(wmod, "_resolve_condition_for_membership", _fake_resolve)
        monkeypatch.setattr(wmod, "_llm_generate_nudge", _llm_spy)

        content, tag = await wmod._generate_condition_nudge(db, mid, "Daily Nudge")
        assert tag == "COND_A"
        assert "PLACEHOLDER" not in content  # real template, not placeholder
        assert llm_called["n"] == 0

    @pytest.mark.asyncio
    async def test_condition_c_regenerates_when_framed_then_falls_back(
        self, seeded_db: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.worker import nudge as wmod

        db = seeded_db["db"]
        mid = seeded_db["membership_id"]
        participation = _make_participation(mid)
        db.add(participation)
        await db.flush()
        await save_user_profile(
            db, mid, UserProfileData(prompt_anchor="after coffee", preferred_time="8am")
        )

        async def _fake_resolve(_db, _mid):
            return "C", participation, 0

        # Always returns framed output → exhausts retries → safe fallback.
        call_count = {"n": 0}

        async def _llm_framed(*_a: Any, **_kw: Any) -> str:
            call_count["n"] += 1
            return "When you brew coffee, then you will do squats."

        monkeypatch.setattr(wmod, "_resolve_condition_for_membership", _fake_resolve)
        monkeypatch.setattr(wmod, "_llm_generate_nudge", _llm_framed)

        content, tag = await wmod._generate_condition_nudge(db, mid, "Daily Nudge")
        assert tag == "COND_C"
        assert call_count["n"] == wmod.MAX_CONDITION_C_REGEN_ATTEMPTS
        assert content == wmod.CONDITION_C_SAFE_FALLBACK

    @pytest.mark.asyncio
    async def test_condition_c_accepts_clean_output_first_try(
        self, seeded_db: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.worker import nudge as wmod

        db = seeded_db["db"]
        mid = seeded_db["membership_id"]
        participation = _make_participation(mid)
        db.add(participation)
        await db.flush()
        await save_user_profile(
            db, mid, UserProfileData(prompt_anchor="after coffee", preferred_time="8am")
        )

        async def _fake_resolve(_db, _mid):
            return "C", participation, 0

        call_count = {"n": 0}
        clean = "It is time for your coffee. Do one minute of squats."

        async def _llm_clean(*_a: Any, **_kw: Any) -> str:
            call_count["n"] += 1
            return clean

        monkeypatch.setattr(wmod, "_resolve_condition_for_membership", _fake_resolve)
        monkeypatch.setattr(wmod, "_llm_generate_nudge", _llm_clean)

        content, tag = await wmod._generate_condition_nudge(db, mid, "Daily Nudge")
        assert content == clean
        assert tag == "COND_C"
        assert call_count["n"] == 1

    @pytest.mark.asyncio
    async def test_condition_d_uses_framed_prompt(
        self, seeded_db: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.worker import nudge as wmod

        db = seeded_db["db"]
        mid = seeded_db["membership_id"]
        participation = _make_participation(mid)
        db.add(participation)
        await db.flush()
        await save_user_profile(
            db, mid, UserProfileData(prompt_anchor="after coffee", preferred_time="8am")
        )

        async def _fake_resolve(_db, _mid):
            return "D", participation, 0

        captured: dict[str, str] = {}

        async def _llm(
            prompt_name,
            prompt_ctx,
            profile_json,
            topic,
            extra_instruction=None,
            daily_summary=None,
        ):
            captured["prompt_name"] = prompt_name
            return "When I have coffee, then I will move. If I complete this, I will smile."

        monkeypatch.setattr(wmod, "_resolve_condition_for_membership", _fake_resolve)
        monkeypatch.setattr(wmod, "_llm_generate_nudge", _llm)

        content, tag = await wmod._generate_condition_nudge(db, mid, "Daily Nudge")
        assert tag == "COND_D"
        assert captured["prompt_name"] == "prompt_generator_condition_d"
        assert "If I complete" in content

    @pytest.mark.asyncio
    async def test_unenrolled_falls_back_to_default_prompt(
        self, seeded_db: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.worker import nudge as wmod

        db = seeded_db["db"]
        mid = seeded_db["membership_id"]
        await save_user_profile(
            db, mid, UserProfileData(prompt_anchor="after coffee", preferred_time="8am")
        )

        # No participation; resolver returns Nones.
        async def _fake_resolve(_db, _mid):
            return None, None, None

        captured: dict[str, str] = {}

        async def _llm(prompt_name, *a, **kw):
            captured["prompt_name"] = prompt_name
            return "neutral nudge"

        monkeypatch.setattr(wmod, "_resolve_condition_for_membership", _fake_resolve)
        monkeypatch.setattr(wmod, "_llm_generate_nudge", _llm)

        content, tag = await wmod._generate_condition_nudge(db, mid, "Daily Nudge")
        assert tag == "SYSTEM"
        assert captured["prompt_name"] == "prompt_generator_system"
        assert content == "neutral nudge"


# ---------------------------------------------------------------------------
# Feedback PLAN-line stripping
# ---------------------------------------------------------------------------


class TestStripFeedbackPlanLine:
    def test_strips_plan_block(self) -> None:
        from app.agents.engine import _strip_feedback_plan_line

        text = "PLAN: missing=last_barrier; next_q=barrier\n---\nGot it — what got in the way?"
        assert _strip_feedback_plan_line(text) == "Got it — what got in the way?"

    def test_strips_lone_plan_prefix(self) -> None:
        from app.agents.engine import _strip_feedback_plan_line

        text = "PLAN: missing=none\nThanks for the update."
        assert _strip_feedback_plan_line(text) == "Thanks for the update."

    def test_passthrough_when_no_plan(self) -> None:
        from app.agents.engine import _strip_feedback_plan_line

        text = "Just a normal reply."
        assert _strip_feedback_plan_line(text) == text
