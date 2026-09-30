"""Hardcoded static feedback script for control conditions A and B.

In conditions A and B the experimental design forbids any LLM intervention
on the feedback path so the user-model cannot implicitly adapt. This module
provides a deterministic, multi-turn check-in script that:

  * asks one question at a time,
  * records the user's free-text answers in
    ``DailyInterventionLog.extracted_state`` (observational only),
  * NEVER proposes profile or memory patches.

State for the current day lives in
``DailyInterventionLog.extracted_state["script"]`` with the shape:

    {
        "step": "ask_attempted" | "ask_followup" | "done",
        "attempted": "yes" | "no" | None,
        "answers": {"attempted_raw": str, "followup_raw": str, ...},
    }

The script is intentionally tiny — three turns at most — to keep the
control-condition workload comparable to a static template without bringing
back any adaptive logic.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DailyInterventionLog, Participation

_INITIAL_PROMPT = (
    "Quick check-in: did you do today's one-minute habit when the nudge came?"
)
_FOLLOWUP_YES = "Nice — what made it easy this time?"
_FOLLOWUP_NO = "Got it — what got in the way?"
_CLOSING = "Thanks for the update. That's all for today."

_YES_TOKENS = {
    "yes",
    "y",
    "yep",
    "yeah",
    "yup",
    "did",
    "done",
    "sure",
    "i did",
    "of course",
}
_NO_TOKENS = {
    "no",
    "n",
    "nope",
    "nah",
    "didn't",
    "didnt",
    "did not",
    "skipped",
    "missed",
    "forgot",
}


def _normalize(text: str) -> str:
    return (text or "").strip().lower()


def _classify_attempted(text: str) -> str | None:
    normalized = _normalize(text)
    if not normalized:
        return None
    if normalized in _YES_TOKENS:
        return "yes"
    if normalized in _NO_TOKENS:
        return "no"
    # Look for whole-word matches at sentence start to avoid e.g. "anywhere".
    first_word = normalized.split()[0].strip(".,!?'\"")
    if first_word in _YES_TOKENS:
        return "yes"
    if first_word in _NO_TOKENS:
        return "no"
    return None


async def _get_today_log(
    db: AsyncSession, membership_id: int
) -> DailyInterventionLog | None:
    """Return today's DailyInterventionLog row for the membership, if any."""
    today = datetime.now(UTC).date()
    result = await db.execute(
        select(DailyInterventionLog)
        .join(
            Participation,
            DailyInterventionLog.participation_id == Participation.id,
        )
        .where(
            Participation.membership_id == membership_id,
            DailyInterventionLog.intervention_date == today,
        )
    )
    return result.scalar_one_or_none()


def _read_script_state(log: DailyInterventionLog | None) -> dict[str, Any]:
    if log is None or not log.extracted_state:
        return {"step": "ask_attempted", "attempted": None, "answers": {}}
    state = dict(log.extracted_state)
    script = state.get("script") or {}
    return {
        "step": script.get("step", "ask_attempted"),
        "attempted": script.get("attempted"),
        "answers": dict(script.get("answers") or {}),
    }


def _write_script_state(
    log: DailyInterventionLog, script_state: dict[str, Any]
) -> None:
    extracted = dict(log.extracted_state or {})
    extracted["script"] = script_state
    log.extracted_state = extracted


async def run_static_feedback(
    db: AsyncSession,
    membership_id: int,
    user_text: str,
    condition: str,
) -> str:
    """Drive a deterministic, no-LLM feedback exchange for conditions A and B.

    Returns the assistant reply text. The caller is responsible for
    persisting it as a Message and committing the surrounding transaction.
    """
    log = await _get_today_log(db, membership_id)
    script_state = _read_script_state(log)
    step = script_state["step"]

    user_input = (user_text or "").strip()

    if step == "ask_attempted":
        if not user_input:
            # First turn (system-triggered): open the check-in.
            reply = _INITIAL_PROMPT
            # No state change — we are still waiting for an answer.
        else:
            attempted = _classify_attempted(user_input)
            script_state["answers"]["attempted_raw"] = user_input
            if attempted is None:
                # Ambiguous answer — re-ask once, still one question.
                reply = (
                    "Just a yes or no is enough: did you do today's one-minute habit?"
                )
            else:
                script_state["attempted"] = attempted
                script_state["step"] = "ask_followup"
                reply = _FOLLOWUP_YES if attempted == "yes" else _FOLLOWUP_NO
    elif step == "ask_followup":
        script_state["answers"]["followup_raw"] = user_input
        script_state["step"] = "done"
        reply = _CLOSING
    else:  # step == "done"
        reply = _CLOSING

    # Persist script state observationally (no profile/memory writes).
    if log is not None:
        script_state["last_condition"] = condition
        _write_script_state(log, script_state)
        db.add(log)
        await db.flush()

    return reply
