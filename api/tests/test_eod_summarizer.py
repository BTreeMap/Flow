"""Tests for the EOD Memory Condensation Agent (cross-condition firewall)."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
import pytest_asyncio
from app.id_utils import generate_project_id, generate_server_msg_id
from app.models import (
    Base,
    Conversation,
    DailyInterventionLog,
    DailySummary,
    Message,
    Participation,
    Project,
    ProjectMembership,
)
from app.services import eod_summarizer as eod
from app.services.eod_summarizer import (
    SUMMARY_WORD_CAP,
    ensure_summaries_up_to,
    load_latest_summary,
    summarize_day,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

_engine = create_async_engine("sqlite+aiosqlite://", echo=False)
_session_factory = async_sessionmaker(_engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def seeded_db() -> AsyncGenerator[dict[str, Any], None]:
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with _session_factory() as session:
        project = Project(id=generate_project_id(), display_name="EOD Test")
        session.add(project)
        await session.flush()
        membership = ProjectMembership(
            project_id=project.id,
            user_id="u_eodtest_000000000000000000",
            status="active",
        )
        session.add(membership)
        await session.flush()
        conv = Conversation(membership_id=membership.id)
        session.add(conv)
        await session.flush()
        participation = Participation(
            membership_id=membership.id,
            study_id="microcoach_v1",
            study_start_date=datetime.now(UTC) - timedelta(days=3),
            timezone="UTC",
        )
        session.add(participation)
        await session.flush()
        yield {
            "db": session,
            "conversation": conv,
            "membership_id": membership.id,
            "participation": participation,
        }
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


def _add_msg(
    db, conv_id: int, role: str, content: str, when: datetime, source: str = "SYSTEM"
) -> Message:
    msg = Message(
        conversation_id=conv_id,
        role=role,
        content=content,
        server_msg_id=generate_server_msg_id(),
        created_at=when,
        condition_source=source,
    )
    db.add(msg)
    return msg


# ---------------------------------------------------------------------------
# Happy path / regen / fallback
# ---------------------------------------------------------------------------


class TestSummarizeDay:
    @pytest.mark.asyncio
    async def test_clean_output_is_persisted_first_try(
        self, seeded_db: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db = seeded_db["db"]
        conv = seeded_db["conversation"]
        participation = seeded_db["participation"]
        target_date = (datetime.now(UTC) - timedelta(days=1)).date()
        _add_msg(
            db,
            conv.id,
            "user",
            "I did the squats today.",
            datetime.combine(target_date, datetime.min.time(), tzinfo=UTC)
            + timedelta(hours=10),
        )
        await db.flush()

        calls = {"n": 0}

        async def _fake_llm(system_text: str, human_text: str) -> str:
            calls["n"] += 1
            return "User completed the squats today; tomorrow's target remains squats."

        monkeypatch.setattr(eod, "_llm_call", _fake_llm)

        row = await summarize_day(db, participation, target_date)
        assert row is not None
        assert row.sterilization_status == "clean"
        assert row.message_count == 1
        assert calls["n"] == 1
        assert "promise" not in row.summary_text.lower()

    @pytest.mark.asyncio
    async def test_framed_output_triggers_regen_then_clean(
        self, seeded_db: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db = seeded_db["db"]
        conv = seeded_db["conversation"]
        participation = seeded_db["participation"]
        target_date = (datetime.now(UTC) - timedelta(days=1)).date()
        _add_msg(
            db,
            conv.id,
            "assistant",
            "When you brew coffee, then you will do squats.",
            datetime.combine(target_date, datetime.min.time(), tzinfo=UTC)
            + timedelta(hours=9),
            source="COND_D",
        )
        await db.flush()

        attempts: list[str] = []
        outputs = iter(
            [
                "When you brew coffee, then you will do squats.",  # framed
                "User completed squats during coffee.",  # clean
            ]
        )

        async def _fake_llm(system_text: str, human_text: str) -> str:
            attempts.append(system_text)
            return next(outputs)

        monkeypatch.setattr(eod, "_llm_call", _fake_llm)

        row = await summarize_day(db, participation, target_date)
        assert row is not None
        assert row.sterilization_status == "regenerated"
        assert len(attempts) == 2
        # The second attempt's prompt must include the additional instruction.
        assert "ADDITIONAL INSTRUCTION" in attempts[1]
        assert "User completed squats" in row.summary_text

    @pytest.mark.asyncio
    async def test_persistent_framing_falls_back_to_skeleton(
        self, seeded_db: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db = seeded_db["db"]
        conv = seeded_db["conversation"]
        participation = seeded_db["participation"]
        target_date = (datetime.now(UTC) - timedelta(days=1)).date()
        _add_msg(
            db,
            conv.id,
            "assistant",
            "If you do this, then I promise you a reward.",
            datetime.combine(target_date, datetime.min.time(), tzinfo=UTC)
            + timedelta(hours=9),
            source="COND_D",
        )
        # A DailyInterventionLog with a "yes" attempt so the skeleton has signal.
        db.add(
            DailyInterventionLog(
                participation_id=participation.id,
                intervention_date=target_date,
                study_day_index=2,
                assigned_condition="C",
                extracted_state={
                    "script": {
                        "step": "done",
                        "attempted": "yes",
                        "answers": {},
                    }
                },
            )
        )
        await db.flush()

        async def _always_framed(system_text: str, human_text: str) -> str:
            return "If you brew coffee, then you will do squats. I promise."

        monkeypatch.setattr(eod, "_llm_call", _always_framed)

        row = await summarize_day(db, participation, target_date)
        assert row is not None
        assert row.sterilization_status == "fallback"
        assert "User completed the habit" in row.summary_text
        # Skeleton must itself be clean.
        from app.services.condition_filters import contains_condition_c_framing

        assert not contains_condition_c_framing(row.summary_text)

    @pytest.mark.asyncio
    async def test_llm_failure_falls_back(
        self, seeded_db: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db = seeded_db["db"]
        participation = seeded_db["participation"]
        target_date = (datetime.now(UTC) - timedelta(days=1)).date()

        async def _boom(system_text: str, human_text: str) -> str:
            raise RuntimeError("simulated LLM outage")

        monkeypatch.setattr(eod, "_llm_call", _boom)

        row = await summarize_day(db, participation, target_date)
        assert row is not None
        assert row.sterilization_status == "fallback"

    @pytest.mark.asyncio
    async def test_idempotent_on_existing_row(
        self, seeded_db: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db = seeded_db["db"]
        participation = seeded_db["participation"]
        target_date = (datetime.now(UTC) - timedelta(days=1)).date()

        async def _llm(_a: str, _b: str) -> str:
            return "User had a quiet day; no new evidence."

        monkeypatch.setattr(eod, "_llm_call", _llm)

        first = await summarize_day(db, participation, target_date)
        second = await summarize_day(db, participation, target_date)
        assert first is not None
        assert second is None
        rows = (await db.execute(select(DailySummary))).scalars().all()
        assert len(rows) == 1

    @pytest.mark.asyncio
    async def test_empty_day_with_no_history_writes_placeholder(
        self, seeded_db: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db = seeded_db["db"]
        participation = seeded_db["participation"]
        target_date = (datetime.now(UTC) - timedelta(days=2)).date()

        async def _llm(_a: str, _b: str) -> str:  # pragma: no cover
            raise AssertionError("LLM must not be called when nothing to summarize")

        monkeypatch.setattr(eod, "_llm_call", _llm)

        row = await summarize_day(db, participation, target_date)
        assert row is not None
        assert row.sterilization_status == "fallback"
        assert "No participant activity" in row.summary_text

    @pytest.mark.asyncio
    async def test_previous_summary_is_passed_into_next_day(
        self, seeded_db: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db = seeded_db["db"]
        conv = seeded_db["conversation"]
        participation = seeded_db["participation"]
        d1 = (datetime.now(UTC) - timedelta(days=2)).date()
        d2 = (datetime.now(UTC) - timedelta(days=1)).date()
        _add_msg(
            db,
            conv.id,
            "user",
            "Did the habit today.",
            datetime.combine(d1, datetime.min.time(), tzinfo=UTC) + timedelta(hours=8),
        )
        _add_msg(
            db,
            conv.id,
            "user",
            "Skipped today, kids were late.",
            datetime.combine(d2, datetime.min.time(), tzinfo=UTC) + timedelta(hours=8),
        )
        await db.flush()

        seen_prev: list[str] = []
        outputs = iter(
            [
                "User completed the habit on day one.",
                "User did not complete the habit on day two due to morning time pressure.",
            ]
        )

        async def _llm(system_text: str, _h: str) -> str:
            seen_prev.append(system_text)
            return next(outputs)

        monkeypatch.setattr(eod, "_llm_call", _llm)

        await summarize_day(db, participation, d1)
        await summarize_day(db, participation, d2)

        # Second call's prompt must contain the first summary verbatim.
        assert "User completed the habit on day one." in seen_prev[1]
        # First call's prompt must NOT contain a fabricated previous summary.
        assert "User completed the habit on day one." not in seen_prev[0]


# ---------------------------------------------------------------------------
# ensure_summaries_up_to
# ---------------------------------------------------------------------------


class TestEnsureSummariesUpTo:
    @pytest.mark.asyncio
    async def test_fills_gap_day_by_day(
        self, seeded_db: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db = seeded_db["db"]
        participation = seeded_db["participation"]

        async def _llm(_a: str, _b: str) -> str:
            return "User had a quiet day."

        monkeypatch.setattr(eod, "_llm_call", _llm)

        through = (datetime.now(UTC) - timedelta(days=1)).date()
        # study_start was 3 days ago → expect 3 summaries (days -3, -2, -1).
        created = await ensure_summaries_up_to(db, participation, through)
        assert created == 3

        # Calling again is a no-op.
        created_again = await ensure_summaries_up_to(db, participation, through)
        assert created_again == 0

    @pytest.mark.asyncio
    async def test_load_latest_summary_returns_most_recent(
        self, seeded_db: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db = seeded_db["db"]
        participation = seeded_db["participation"]

        # Manually insert two rows out of order.
        db.add(
            DailySummary(
                participation_id=participation.id,
                summary_date=date(2026, 1, 1),
                summary_text="older",
                sterilization_status="clean",
            )
        )
        db.add(
            DailySummary(
                participation_id=participation.id,
                summary_date=date(2026, 1, 5),
                summary_text="newer",
                sterilization_status="clean",
            )
        )
        await db.flush()
        latest = await load_latest_summary(db, participation.id)
        assert latest == "newer"


# ---------------------------------------------------------------------------
# Engine integration: Condition C/D chat turn receives the summary
# ---------------------------------------------------------------------------


class TestEngineSummaryInjection:
    @pytest.mark.asyncio
    async def test_condition_c_turn_loads_latest_summary(
        self, seeded_db: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.agents import engine as engine_mod
        from app.schemas.patches import UserProfileData
        from app.services.profile_service import save_user_profile

        db = seeded_db["db"]
        conv = seeded_db["conversation"]
        mid = seeded_db["membership_id"]
        participation = seeded_db["participation"]

        await save_user_profile(
            db,
            mid,
            UserProfileData(prompt_anchor="after coffee", preferred_time="8am"),
        )
        db.add(
            DailySummary(
                participation_id=participation.id,
                summary_date=(datetime.now(UTC) - timedelta(days=1)).date(),
                summary_text="User completed squats yesterday; no barriers reported.",
                sterilization_status="clean",
            )
        )
        await db.flush()

        async def _fake_ctx(db, membership_id, current_date):
            return "C", participation, 1

        monkeypatch.setattr(engine_mod, "_get_active_condition_context", _fake_ctx)

        # Spy: make sure ensure_summaries_up_to is invoked and load returns
        # the stored summary. We patch the imported names inside the engine
        # module's lazily-imported namespace by patching the source module.
        ensure_called = {"n": 0}

        from app.services import eod_summarizer

        orig_ensure = eod_summarizer.ensure_summaries_up_to

        async def _spy_ensure(db_, part_, through_):
            ensure_called["n"] += 1
            return await orig_ensure(db_, part_, through_)

        monkeypatch.setattr(eod_summarizer, "ensure_summaries_up_to", _spy_ensure)

        user_msg = Message(
            conversation_id=conv.id,
            role="user",
            content="hi",
            server_msg_id=generate_server_msg_id(),
        )
        db.add(user_msg)
        await db.flush()
        text, _decision, _debug, _p = await engine_mod.process_turn(
            db=db,
            conversation=conv,
            membership_id=mid,
            user_msg=user_msg,
            user_text="hi",
        )
        assert text  # stub response, non-empty
        assert ensure_called["n"] == 1

    @pytest.mark.asyncio
    async def test_condition_a_turn_does_not_load_summary(
        self, seeded_db: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.agents import engine as engine_mod
        from app.schemas.patches import UserProfileData
        from app.services.profile_service import save_user_profile

        db = seeded_db["db"]
        conv = seeded_db["conversation"]
        mid = seeded_db["membership_id"]
        participation = seeded_db["participation"]

        await save_user_profile(
            db,
            mid,
            UserProfileData(prompt_anchor="after coffee", preferred_time="8am"),
        )

        async def _fake_ctx(db, membership_id, current_date):
            return "A", participation, 1

        monkeypatch.setattr(engine_mod, "_get_active_condition_context", _fake_ctx)

        from app.services import eod_summarizer

        async def _explode(*_a: Any, **_kw: Any) -> None:
            raise AssertionError(
                "ensure_summaries_up_to must NOT run on Condition A turns"
            )

        monkeypatch.setattr(eod_summarizer, "ensure_summaries_up_to", _explode)

        user_msg = Message(
            conversation_id=conv.id,
            role="user",
            content="hi",
            server_msg_id=generate_server_msg_id(),
        )
        db.add(user_msg)
        await db.flush()
        # Must complete without invoking the summarizer.
        await engine_mod.process_turn(
            db=db,
            conversation=conv,
            membership_id=mid,
            user_msg=user_msg,
            user_text="hi",
        )


# ---------------------------------------------------------------------------
# Worker integration: nudge generator passes summary to LLM in C and D
# ---------------------------------------------------------------------------


class TestWorkerSummaryInjection:
    @pytest.mark.asyncio
    async def test_condition_d_nudge_receives_daily_summary(
        self, seeded_db: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.schemas.patches import UserProfileData
        from app.services.profile_service import save_user_profile
        from app.worker import nudge as wmod

        db = seeded_db["db"]
        mid = seeded_db["membership_id"]
        participation = seeded_db["participation"]

        await save_user_profile(
            db, mid, UserProfileData(prompt_anchor="after coffee", preferred_time="8am")
        )
        db.add(
            DailySummary(
                participation_id=participation.id,
                summary_date=(datetime.now(UTC) - timedelta(days=1)).date(),
                summary_text="User completed squats yesterday at coffee.",
                sterilization_status="clean",
            )
        )
        await db.flush()

        async def _fake_resolve(_db, _mid):
            return "D", participation, 1

        captured: dict[str, Any] = {}

        async def _llm(
            prompt_name,
            prompt_ctx,
            profile_json,
            topic,
            extra_instruction=None,
            daily_summary=None,
        ):
            captured["daily_summary"] = daily_summary
            captured["prompt_name"] = prompt_name
            return "When I have coffee, then I will move. If I complete this, I will smile."

        monkeypatch.setattr(wmod, "_resolve_condition_for_membership", _fake_resolve)
        monkeypatch.setattr(wmod, "_llm_generate_nudge", _llm)

        _content, tag = await wmod._generate_condition_nudge(db, mid, "Daily Nudge")
        assert tag == "COND_D"
        assert captured["daily_summary"] == (
            "User completed squats yesterday at coffee."
        )

    @pytest.mark.asyncio
    async def test_condition_a_nudge_does_not_load_summary(
        self, seeded_db: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.worker import nudge as wmod

        db = seeded_db["db"]
        mid = seeded_db["membership_id"]
        participation = seeded_db["participation"]

        async def _fake_resolve(_db, _mid):
            return "A", participation, 0

        from app.services import eod_summarizer

        async def _explode(*_a: Any, **_kw: Any) -> None:
            raise AssertionError("summary loader must NOT run on Condition A nudges")

        monkeypatch.setattr(wmod, "_resolve_condition_for_membership", _fake_resolve)
        monkeypatch.setattr(eod_summarizer, "ensure_summaries_up_to", _explode)

        # Static template path — no LLM, no summarizer.
        content, tag = await wmod._generate_condition_nudge(db, mid, "Daily Nudge")
        assert tag == "COND_A"
        assert content


# ---------------------------------------------------------------------------
# Word cap helper
# ---------------------------------------------------------------------------


def test_truncate_to_word_cap_enforces_limit() -> None:
    from app.services.eod_summarizer import _truncate_to_word_cap

    long_text = " ".join(["word"] * (SUMMARY_WORD_CAP + 20))
    result = _truncate_to_word_cap(long_text)
    assert len(result.split()) <= SUMMARY_WORD_CAP + 1  # the trailing "."
    assert result.endswith(".")


def test_truncate_to_word_cap_passthrough_short_text() -> None:
    from app.services.eod_summarizer import _truncate_to_word_cap

    short = "User did the habit."
    assert _truncate_to_word_cap(short) == short
