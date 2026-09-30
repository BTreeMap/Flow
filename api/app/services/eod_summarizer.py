"""End-of-day Memory Condensation Agent — the cross-condition semantic firewall.

Produces a strict 1–2 sentence clinical summary of one study day and stores
it in :class:`DailySummary`. The summary is later injected into Condition
C and Condition D LLM prompts so they retain multi-day memory without ever
seeing the raw "if/then" framing produced under Condition B / D.

Key invariants:

* The summarizer is the ONLY writer of :class:`DailySummary`. It is NOT
  subject to the Router single-writer rule that governs profile / memory
  writes — its output is internal infrastructure (never user-visible) and
  proposes no patches.
* Every persisted summary has passed the same Condition-C framing regex
  used by the Coach and the notification worker, or has been replaced by
  a deterministic skeleton built from
  ``DailyInterventionLog.extracted_state`` when the model could not
  produce clean output.
* Synthesis is incremental: the previous day's summary is fed back into
  the prompt so the LLM merges, not appends.

Usage:

    await ensure_summaries_up_to(db, participation, through_date)
    summary = await load_latest_summary(db, participation_id)
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import config
from app.llm import make_chat_llm
from app.logging_conf import LLMLoggingCallbackHandler
from app.models import (
    DailyInterventionLog,
    DailySummary,
    Message,
    Participation,
)
from app.prompt_loader import load_prompt, prompt_hash
from app.services.condition_filters import contains_condition_c_framing
from app.services.prompt_context import get_prompt_context_for_membership

logger = logging.getLogger(__name__)

PROMPT_NAME = "eod_summarizer_system"
MAX_REGEN_ATTEMPTS = 2
SUMMARY_WORD_CAP = 60
LLM_TIMEOUT_SECONDS = 20
EMPTY_LOG_PLACEHOLDER = "(no chat messages on this day)"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def load_latest_summary(db: AsyncSession, participation_id: int) -> str | None:
    """Return the most recent persisted summary text for a participation."""
    result = await db.execute(
        select(DailySummary)
        .where(DailySummary.participation_id == participation_id)
        .order_by(DailySummary.summary_date.desc())
        .limit(1)
    )
    row = result.scalar_one_or_none()
    return row.summary_text if row is not None else None


async def ensure_summaries_up_to(
    db: AsyncSession,
    participation: Participation,
    through_date: date,
) -> int:
    """Lazily produce any missing :class:`DailySummary` rows up to ``through_date``.

    Walks day-by-day from the day after ``study_start_date`` (or the day
    after the latest existing summary) through ``through_date`` inclusive.
    Returns the number of summaries newly created.

    Designed to be called on the hot path: the per-day work is cheap (one
    short LLM call) and after the first call of a given day the loop is a
    no-op. A future cron job can call this same entry point.
    """
    start_date = participation.study_start_date.date()
    if through_date < start_date:
        return 0

    # Find the latest existing summary so we only fill gaps.
    latest_row = (
        await db.execute(
            select(DailySummary)
            .where(DailySummary.participation_id == participation.id)
            .order_by(DailySummary.summary_date.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    cursor = latest_row.summary_date + timedelta(days=1) if latest_row else start_date

    created = 0
    safety_budget = 30  # never run away on first-time catch-up of a long history
    while cursor <= through_date and safety_budget > 0:
        safety_budget -= 1
        try:
            row = await summarize_day(db, participation, cursor)
            if row is not None:
                created += 1
        except Exception:
            logger.exception(
                "EOD summarization failed for participation_id=%s date=%s",
                participation.id,
                cursor,
            )
            # Don't loop forever on persistent failures: stop catch-up for
            # this call; the next call will retry from the same cursor.
            break
        cursor = cursor + timedelta(days=1)
    return created


async def summarize_day(
    db: AsyncSession,
    participation: Participation,
    summary_date: date,
) -> DailySummary | None:
    """Produce and persist the summary for one UTC day. Idempotent.

    Returns the persisted row, or ``None`` if a summary already existed.
    """
    # Idempotency check.
    existing = (
        await db.execute(
            select(DailySummary).where(
                DailySummary.participation_id == participation.id,
                DailySummary.summary_date == summary_date,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return None

    membership_id = participation.membership_id

    # Resolve conversation id (we summarize that membership's single
    # conversation, which is the 1:1 chat thread).
    conversation_id = await _get_conversation_id(db, membership_id)

    # Load the day's chat log (UTC day boundaries) — chronological.
    messages: list[Message] = []
    if conversation_id is not None:
        day_start = datetime.combine(summary_date, datetime.min.time(), tzinfo=UTC)
        day_end = day_start + timedelta(days=1)
        result = await db.execute(
            select(Message)
            .where(
                Message.conversation_id == conversation_id,
                Message.created_at >= day_start,
                Message.created_at < day_end,
            )
            .order_by(Message.id.asc())
        )
        messages = list(result.scalars().all())

    # Load previous summary for incremental synthesis.
    prev_summary = await load_latest_summary(db, participation.id)
    # Load today's DailyInterventionLog for the deterministic fallback path.
    intervention_log = (
        await db.execute(
            select(DailyInterventionLog).where(
                DailyInterventionLog.participation_id == participation.id,
                DailyInterventionLog.intervention_date == summary_date,
            )
        )
    ).scalar_one_or_none()

    summary_text, status = await _produce_summary(
        db=db,
        membership_id=membership_id,
        summary_date=summary_date,
        previous_summary=prev_summary,
        messages=messages,
        intervention_log=intervention_log,
    )

    row = DailySummary(
        participation_id=participation.id,
        summary_date=summary_date,
        summary_text=summary_text,
        previous_summary_text=prev_summary,
        message_count=len(messages),
        sterilization_status=status,
        prompt_sha256=prompt_hash(PROMPT_NAME),
    )
    db.add(row)
    await db.flush()
    return row


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


async def _get_conversation_id(db: AsyncSession, membership_id: int) -> int | None:
    """Resolve the (unique) conversation id for a membership."""
    from app.models import Conversation  # local import to avoid cycle

    res = await db.execute(
        select(Conversation.id).where(Conversation.membership_id == membership_id)
    )
    return res.scalar_one_or_none()


def _format_chat_log(messages: list[Message]) -> str:
    if not messages:
        return EMPTY_LOG_PLACEHOLDER
    lines: list[str] = []
    for msg in messages:
        role = "USER" if msg.role == "user" else "BOT"
        # Truncate any extremely long bot turns to keep the prompt bounded;
        # the sterilization rules apply regardless of length.
        content = (msg.content or "").strip().replace("\n", " ")
        if len(content) > 400:
            content = content[:400] + "…"
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


def _truncate_to_word_cap(text: str, word_cap: int = SUMMARY_WORD_CAP) -> str:
    words = text.split()
    if len(words) <= word_cap:
        return text.strip()
    return " ".join(words[:word_cap]).rstrip(",;:.") + "."


def _deterministic_fallback(
    summary_date: date,
    previous_summary: str | None,
    intervention_log: DailyInterventionLog | None,
) -> str:
    """Build a safe, clinical summary without involving the LLM.

    Used when the LLM either fails or produces output that keeps tripping
    the framing regex after retries.
    """
    extracted: dict[str, Any] = {}
    condition = "unknown"
    if intervention_log is not None:
        extracted = intervention_log.extracted_state or {}
        condition = intervention_log.assigned_condition or "unknown"

    script = extracted.get("script") if isinstance(extracted, dict) else None
    attempted_raw: str | None = None
    if isinstance(script, dict):
        attempted_raw = script.get("attempted")

    if attempted_raw == "yes":
        outcome = "User completed the habit"
    elif attempted_raw == "no":
        outcome = "User did not complete the habit"
    else:
        outcome = "No clear behavioral signal collected"

    base = f"{outcome} on {summary_date.isoformat()} (condition {condition})."
    if previous_summary:
        # Keep one short clause of continuity.
        cont = previous_summary.split(".")[0].strip()
        if cont and cont.lower() not in base.lower():
            base = f"{base} Prior state: {cont}."
    return _truncate_to_word_cap(base)


async def _llm_call(system_text: str, human_text: str) -> str:
    llm_key = config.get_openai_api_key()
    if not llm_key:
        raise RuntimeError("OpenAI API key not configured for EOD summarizer")
    llm = make_chat_llm(
        model=config.get_llm_model(),
        api_key=llm_key,
        callbacks=[LLMLoggingCallbackHandler()],
    )
    res = await asyncio.wait_for(
        llm.ainvoke(
            [SystemMessage(content=system_text), HumanMessage(content=human_text)]
        ),
        timeout=LLM_TIMEOUT_SECONDS,
    )
    return str(res.content).strip()


async def _produce_summary(
    *,
    db: AsyncSession,
    membership_id: int,
    summary_date: date,
    previous_summary: str | None,
    messages: list[Message],
    intervention_log: DailyInterventionLog | None,
) -> tuple[str, str]:
    """Run the summarizer with regex-gated regen + deterministic fallback.

    Returns ``(summary_text, sterilization_status)``.
    """
    # Even on a totally empty day we still want a row, so the next day's
    # incremental synthesis sees a continuous chain.
    if not messages and previous_summary is None and intervention_log is None:
        return (
            f"No participant activity recorded on {summary_date.isoformat()}.",
            "fallback",
        )

    # Build prompt template substitutions.
    prompt_ctx = await get_prompt_context_for_membership(db, membership_id)
    import string

    base_system = load_prompt(PROMPT_NAME)
    substitutions = {
        **prompt_ctx,
        "summary_date": summary_date.isoformat(),
        "previous_memory": previous_summary or "(none — first day)",
        "daily_chat_log": _format_chat_log(messages),
    }
    system_text = string.Template(base_system).safe_substitute(substitutions)
    human_text = "Produce the sterilized summary now."

    extra_instruction = ""
    for attempt in range(MAX_REGEN_ATTEMPTS + 1):
        prompt = system_text + (
            f"\n\nADDITIONAL INSTRUCTION:\n{extra_instruction}"
            if extra_instruction
            else ""
        )
        try:
            candidate = await _llm_call(prompt, human_text)
        except Exception as exc:
            logger.error(
                "EOD summarizer LLM call failed on attempt %d: %s", attempt, exc
            )
            return (
                _deterministic_fallback(
                    summary_date, previous_summary, intervention_log
                ),
                "fallback",
            )
        candidate = _truncate_to_word_cap(candidate)
        if not contains_condition_c_framing(candidate):
            return candidate, ("clean" if attempt == 0 else "regenerated")
        logger.warning(
            "EOD summary contained forbidden framing on attempt %d; regenerating",
            attempt,
        )
        extra_instruction = (
            "Your previous output contained forbidden framing vocabulary "
            "(if/then, when/then, commit, commitment, contract, promise, "
            "reward, bet, motivate, motivated). Rewrite without any of those "
            "words and without preserving the bot's framing. Use neutral, "
            "state-based, clinical observations only. One or two sentences, "
            "≤60 words."
        )

    logger.error(
        "EOD summarizer could not produce clean output after %d attempts; "
        "falling back to deterministic skeleton",
        MAX_REGEN_ATTEMPTS + 1,
    )
    return (
        _deterministic_fallback(summary_date, previous_summary, intervention_log),
        "fallback",
    )


__all__ = [
    "MAX_REGEN_ATTEMPTS",
    "SUMMARY_WORD_CAP",
    "ensure_summaries_up_to",
    "load_latest_summary",
    "summarize_day",
]
