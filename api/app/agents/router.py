"""Coordinator router — structured output, no user-visible text (§4.1).

The router is NOT a LangChain agent; it is a single LLM call that returns
a Pydantic ``RouteDecision``.  It must never produce user-facing text.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate

from app.prompt_loader import load_prompt
from app.schemas.router import RouteDecision

logger = logging.getLogger(__name__)

# Router prompt loaded from file
ROUTER_SYSTEM_PROMPT = load_prompt("router_system")

ROUTER_USER_TEMPLATE = (
    "Current conversation sub-state: {sub_state}\n"
    "Profile completeness: {profile_summary}\n"
    "User message: {user_text}\n"
    "Return the route."
)

_router_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", ROUTER_SYSTEM_PROMPT),
        ("human", ROUTER_USER_TEMPLATE),
    ]
)


def route_turn(
    user_text: str,
    sub_state: str,
    profile_summary: str,
    llm: BaseChatModel | None = None,
) -> RouteDecision:
    """Determine the routing decision for a user turn.

    When *llm* is ``None`` the router falls back to deterministic
    state-based routing that mirrors the legacy ``ConversationFlow``
    behaviour exactly (§3.1 critical invariant: default to INTAKE).
    """
    if llm is not None:
        return _route_via_llm(llm, user_text, sub_state, profile_summary)
    return _route_deterministic(sub_state)


def _route_deterministic(sub_state: str) -> RouteDecision:
    """Pure state-gate router matching legacy §3.1 / §4.1 semantics.

    * If sub-state is ``FEEDBACK`` → route to FEEDBACK.
    * Otherwise (empty, INTAKE, or any unknown value) → route to INTAKE.
    """
    if sub_state == "FEEDBACK":
        return RouteDecision(route="FEEDBACK", reason="sub-state is FEEDBACK")
    return RouteDecision(route="INTAKE", reason="default to INTAKE per §3.1")


def _route_via_llm(
    llm: BaseChatModel,
    user_text: str,
    sub_state: str,
    profile_summary: str,
) -> RouteDecision:
    """Use the LLM with structured output to produce a ``RouteDecision``."""
    structured = llm.with_structured_output(RouteDecision)
    result: Any = (_router_prompt | structured).invoke(
        {
            "sub_state": sub_state,
            "profile_summary": profile_summary,
            "user_text": user_text,
        }
    )
    if not isinstance(result, RouteDecision):
        logger.warning(
            "Router LLM returned unexpected type %s; falling back", type(result)
        )
        return _route_deterministic(sub_state)
    logger.info("Router decision: %s (reason: %s)", result.route, result.reason)
    return result
