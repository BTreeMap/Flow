"""Routing helpers for the turn engine — deterministic + LLM routing and condition resolution."""

from __future__ import annotations

import logging
import string
from datetime import date
from functools import lru_cache

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Participation
from app.prompt_loader import load_prompt
from app.schemas.patches import UserProfileData
from app.schemas.router import RouteDecision
from app.services.crypto import (
    CryptoConfigurationError,
    get_randomization_key,
)
from app.services.randomization import get_daily_condition

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Router (structured output, no user-visible text)
# ---------------------------------------------------------------------------

ROUTER_SYSTEM_PROMPT = load_prompt("router_system")


def route_turn_deterministic(
    profile: UserProfileData,
    conv_state: str,
) -> RouteDecision:
    """Deterministic routing based on profile completeness and state."""
    # If required onboarding fields missing → INTAKE
    if not profile.prompt_anchor or not profile.preferred_time:
        return RouteDecision(
            route="INTAKE", reason="required onboarding fields missing"
        )

    # If in feedback protocol → FEEDBACK
    if conv_state == "FEEDBACK":
        return RouteDecision(route="FEEDBACK", reason="currently in feedback protocol")

    # Default → COACH
    return RouteDecision(route="COACH", reason="profile complete, normal conversation")


def route_turn_llm(
    llm: BaseChatModel,
    profile_summary: str,
    memory_summary: str,
    conv_state: str,
    user_text: str,
    time_context: dict[str, str] | None = None,
) -> RouteDecision:
    """Use LLM with structured output for routing."""
    # Pass schema dict to get a dict back, avoiding Pydantic serialization issues in LangChain
    structured = llm.with_structured_output(RouteDecision.model_json_schema())

    # Pre-substitute $-variables in the system prompt (safe against any {}
    # content in the prompt file, e.g. JSON examples).
    system_text = string.Template(ROUTER_SYSTEM_PROMPT).safe_substitute(
        time_context or {}
    )

    tc = time_context or {}
    human_text = (
        f"Current local date: {tc.get('current_date', 'unknown')}\n"
        f"Current local time: {tc.get('current_time', 'unknown')}\n"
        f"Timezone: {tc.get('timezone', 'unknown')}\n"
        f"Profile summary: {profile_summary}\n"
        f"Memory summary: {memory_summary}\n"
        f"Conversation state: {conv_state}\n"
        f"User message: {user_text}\n"
        "Return the route."
    )

    messages = [SystemMessage(content=system_text), HumanMessage(content=human_text)]
    try:
        result = structured.invoke(messages)
    except Exception:
        logger.exception("Router LLM invocation failed")
        return RouteDecision(route="COACH", reason="LLM invocation failed")

    if isinstance(result, dict):
        try:
            decision = RouteDecision.model_validate(result)
        except Exception:
            logger.warning("Failed to parse RouteDecision from dict: %s", result)
            return RouteDecision(route="COACH", reason="LLM fallback (parse error)")
    elif isinstance(result, RouteDecision):
        decision = result
    else:
        return RouteDecision(route="COACH", reason="LLM fallback (unknown type)")

    # The LLM is never allowed to assign the synthetic STATIC_* routes —
    # those are markers the engine itself sets when bypassing the LLM.
    if decision.route not in {"INTAKE", "FEEDBACK", "COACH"}:
        logger.warning(
            "Router LLM returned non-specialist route %s; coercing to COACH",
            decision.route,
        )
        return RouteDecision(route="COACH", reason=f"coerced from {decision.route}")
    return decision


@lru_cache(maxsize=1)
def _get_randomization_key() -> bytes:
    try:
        return get_randomization_key()
    except CryptoConfigurationError as exc:
        raise RuntimeError(
            "FLOW_CRYPTO_MASTER_KEY must be a valid 32-byte Base64URL key "
            "for participation randomization"
        ) from exc


async def _get_active_condition_context(
    db: AsyncSession,
    membership_id: int,
    current_date: date,
) -> tuple[str | None, Participation | None, int | None]:
    """Resolve the active experimental condition for a membership on a given date."""
    participation_result = await db.execute(
        select(Participation)
        .where(Participation.membership_id == membership_id)
        .order_by(Participation.id.desc())
        .limit(1)
    )
    participation = participation_result.scalar_one_or_none()
    if participation is None:
        return None, None, None

    study_day_index = (current_date - participation.study_start_date.date()).days

    key = _get_randomization_key()
    condition = get_daily_condition(
        participation_id=participation.id,
        study_start_date=participation.study_start_date,
        current_date=current_date,
        key=key,
    )
    return condition, participation, study_day_index
