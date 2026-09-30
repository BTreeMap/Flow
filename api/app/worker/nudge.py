"""Nudge / prompt generation for the notification worker.

This module owns all condition-aware nudge generation. It imports the
LLM/profile/prompt-context dependencies into *its own* module globals so that
tests which patch ``app.worker.nudge.<name>`` (or monkeypatch attributes on this
module) take effect on the functions defined here.
"""

from __future__ import annotations

import asyncio
import json
import logging
import string
from datetime import UTC, datetime, timedelta

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import select

from app import config
from app.llm import make_chat_llm
from app.logging_conf import LLMLoggingCallbackHandler
from app.models import (
    DailyInterventionLog,
    Participation,
)
from app.prompt_loader import load_prompt
from app.services.condition_filters import contains_condition_c_framing
from app.services.crypto import (
    CryptoConfigurationError,
    get_randomization_key,
)
from app.services.intervention_config import get_static_intervention
from app.services.profile_service import load_user_profile
from app.services.prompt_context import get_prompt_context_for_membership
from app.services.randomization import get_daily_condition

logger = logging.getLogger(__name__)

MAX_CONDITION_C_REGEN_ATTEMPTS = 3
CONDITION_C_REGEN_INSTRUCTION = (
    "Your previous output contained forbidden conditional planning, commitment, "
    "or reward framing. Regenerate the nudge with NO if/then or when/then "
    "structure, NO commitment contract, NO promise, NO reward language, and "
    "NONE of the words: commit, commitment, contract, promise, reward, bet. "
    "Produce one or two sentences. Mention the user's anchor as the trigger, "
    "and suggest a single one-minute physical action. Be neutral and direct."
)
CONDITION_C_SAFE_FALLBACK = (
    "When your next routine begins, take one minute to move your body — a short "
    "set of squats or a brisk walk in place."
)
PROMPT_GENERATOR_DEFAULT = "prompt_generator_system"
PROMPT_GENERATOR_BY_CONDITION = {
    "C": "prompt_generator_condition_c",
    "D": "prompt_generator_condition_d",
}


def _condition_to_source_tag(condition: str | None) -> str:
    """Map an experimental condition letter to the Message.condition_source tag."""
    if not condition:
        return "SYSTEM"
    return f"COND_{condition.upper()}"


def _randomization_key() -> bytes | None:
    """Return the derived randomization key, or None if unconfigured.

    The worker is permissive about a missing master key (it falls back to the
    generic prompt) so that an unconfigured environment still produces
    useful nudges instead of failing every fire.
    """
    try:
        return get_randomization_key()
    except CryptoConfigurationError:
        return None


async def _resolve_condition_for_membership(
    db, membership_id: int
) -> tuple[str | None, Participation | None, int | None]:
    """Resolve today's experimental condition for a membership.

    Returns (condition, participation, study_day_index). Any of these may be
    None when the membership is not enrolled in the study or the
    cryptographic master key is not configured.
    """
    result = await db.execute(
        select(Participation)
        .where(Participation.membership_id == membership_id)
        .order_by(Participation.id.desc())
        .limit(1)
    )
    participation = result.scalar_one_or_none()
    if participation is None:
        return None, None, None

    key = _randomization_key()
    if key is None:
        return None, participation, None

    today = datetime.now(UTC).date()
    study_day_index = (today - participation.study_start_date.date()).days
    condition = get_daily_condition(
        participation_id=participation.id,
        study_start_date=participation.study_start_date,
        current_date=today,
        key=key,
    )
    return condition, participation, study_day_index


async def _ensure_daily_intervention_log(
    db,
    participation: Participation,
    study_day_index: int,
    condition: str,
) -> None:
    """Make sure today's DailyInterventionLog exists, mirroring the engine path."""
    today = datetime.now(UTC).date()
    result = await db.execute(
        select(DailyInterventionLog).where(
            DailyInterventionLog.participation_id == participation.id,
            DailyInterventionLog.intervention_date == today,
        )
    )
    if result.scalar_one_or_none() is not None:
        return
    db.add(
        DailyInterventionLog(
            participation_id=participation.id,
            intervention_date=today,
            study_day_index=study_day_index,
            assigned_condition=condition,
            extracted_state={},
        )
    )
    await db.flush()


async def _llm_generate_nudge(
    prompt_name: str,
    prompt_ctx: dict[str, str],
    profile_json: str,
    topic: str,
    extra_instruction: str | None = None,
    daily_summary: str | None = None,
) -> str:
    """Invoke the LLM with the given prompt template. Raises on failure."""
    llm_key = config.get_openai_api_key()
    if not llm_key:
        raise RuntimeError("OpenAI API key not configured")

    system_text = load_prompt(prompt_name)
    system_text = string.Template(system_text).safe_substitute(prompt_ctx)
    if extra_instruction:
        system_text = f"{system_text}\n\nADDITIONAL INSTRUCTION:\n{extra_instruction}"

    human_parts = [f"Topic: {topic}", f"User profile: {profile_json}"]
    if daily_summary:
        human_parts.append(
            "Sterilized cross-day memory (clinical, no framing) — use for "
            f"continuity but do not imitate its phrasing:\n{daily_summary}"
        )
    human_parts.append("Generate the nudge.")
    messages = [
        SystemMessage(content=system_text),
        HumanMessage(content="\n".join(human_parts)),
    ]
    llm = make_chat_llm(
        model=config.get_llm_model(),
        api_key=llm_key,
        callbacks=[LLMLoggingCallbackHandler()],
    )
    res = await asyncio.wait_for(llm.ainvoke(messages), timeout=15)
    return str(res.content).strip()


async def _generate_condition_nudge(
    db, membership_id: int, topic: str
) -> tuple[str, str | None]:
    """Generate a nudge respecting the active experimental condition.

    Returns ``(content, condition_source_tag)`` where ``condition_source_tag``
    is one of ``"COND_A"``, ``"COND_B"``, ``"COND_C"``, ``"COND_D"`` or
    ``"SYSTEM"`` for unenrolled / fallback cases.
    """
    condition, participation, study_day_index = await _resolve_condition_for_membership(
        db, membership_id
    )

    # Conditions A and B: bypass the LLM entirely with a static template.
    if (
        condition in {"A", "B"}
        and participation is not None
        and study_day_index is not None
    ):
        await _ensure_daily_intervention_log(
            db, participation, study_day_index, condition
        )
        try:
            content = get_static_intervention(
                condition, participation.id, study_day_index
            )
        except Exception as exc:
            logger.error("Static intervention lookup failed for %s: %s", condition, exc)
            content = f"{topic}"
        return content, _condition_to_source_tag(condition)

    # All LLM paths share the same prompt context + profile shape.
    profile = await load_user_profile(db, membership_id)
    prompt_ctx = await get_prompt_context_for_membership(db, membership_id)
    profile_data = profile.model_dump()
    profile_data.pop("preferred_time", None)
    profile_json = json.dumps(
        {k: v for k, v in profile_data.items() if v is not None}, default=str
    )

    prompt_name = (
        PROMPT_GENERATOR_BY_CONDITION.get(condition) if condition else None
    ) or PROMPT_GENERATOR_DEFAULT

    # For Conditions C and D, fetch the sterilized cross-day memory so the
    # nudge generator has multi-day context without seeing raw assistant
    # framing from prior days. This is the "semantic firewall" — both
    # conditions read the same clinical summary.
    daily_summary: str | None = None
    if condition in {"C", "D"} and participation is not None:
        try:
            from app.services.eod_summarizer import (
                ensure_summaries_up_to,
                load_latest_summary,
            )

            yesterday = datetime.now(UTC).date() - timedelta(days=1)
            await ensure_summaries_up_to(db, participation, yesterday)
            daily_summary = await load_latest_summary(db, participation.id)
        except Exception:
            logger.exception("Failed to ensure/load EOD summary for nudge generation")

    # Condition D and the default path: single LLM call, return as-is.
    if condition != "C":
        if (
            condition == "D"
            and participation is not None
            and study_day_index is not None
        ):
            await _ensure_daily_intervention_log(
                db, participation, study_day_index, condition
            )
        try:
            content = await _llm_generate_nudge(
                prompt_name,
                prompt_ctx,
                profile_json,
                topic,
                daily_summary=daily_summary,
            )
        except Exception as exc:
            logger.error("LLM nudge generation failed (%s): %s", prompt_name, exc)
            content = f"{topic} (Generation failed)"
        return content, _condition_to_source_tag(condition)

    # Condition C: generate, regex-filter, regenerate up to N times, then
    # fall back to a safe neutral string. This protects against the LLM
    # implicitly drifting toward Condition D's framing.
    if participation is not None and study_day_index is not None:
        await _ensure_daily_intervention_log(
            db, participation, study_day_index, condition
        )
    extra: str | None = None
    last_content: str | None = None
    for attempt in range(MAX_CONDITION_C_REGEN_ATTEMPTS):
        try:
            candidate = await _llm_generate_nudge(
                prompt_name,
                prompt_ctx,
                profile_json,
                topic,
                extra_instruction=extra,
                daily_summary=daily_summary,
            )
        except Exception as exc:
            logger.error("Condition C LLM call failed on attempt %d: %s", attempt, exc)
            break
        last_content = candidate
        if not contains_condition_c_framing(candidate):
            return candidate, _condition_to_source_tag(condition)
        logger.warning(
            "Condition C output contained framing on attempt %d; regenerating",
            attempt,
        )
        extra = CONDITION_C_REGEN_INSTRUCTION

    logger.error(
        "Condition C output still contained framing after %d attempts; using safe fallback",
        MAX_CONDITION_C_REGEN_ATTEMPTS,
    )
    _ = last_content  # kept for log context only
    return CONDITION_C_SAFE_FALLBACK, _condition_to_source_tag(condition)


async def _generate_custom_prompt(db, membership_id: int, topic: str) -> str:
    """Backwards-compatible wrapper used by older call sites and tests.

    Prefer :func:`_generate_condition_nudge` when you need the condition tag
    alongside the content.
    """
    content, _tag = await _generate_condition_nudge(db, membership_id, topic)
    return content


def _to_feedback_poll_actions(actions: list[dict] | None) -> list[dict[str, str]]:
    valid_actions: list[dict[str, str]] = []
    for action in actions or []:
        if not isinstance(action, dict):
            continue
        action_id = str(action.get("action") or "").strip()
        action_title = str(action.get("title") or "").strip()
        if action_id and action_title:
            valid_actions.append({"id": action_id, "title": action_title})
    return valid_actions
