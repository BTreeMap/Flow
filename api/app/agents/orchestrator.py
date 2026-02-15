"""Turn-level orchestrator pipeline (§4.1, Pattern 4).

Implements the five-step turn handler:
1. Load runtime state and compute state summary for the router.
2. Get ``RouteDecision`` from the coordinator.
3. Invoke the chosen agent executor.
4. Persist assistant output and updated state.
5. Return the assistant text (SSE emission is the caller's responsibility).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage

from app.agents.feedback import create_feedback_agent, run_feedback
from app.agents.intake import create_intake_agent, run_intake
from app.agents.router import route_turn
from app.engine.flow import MAX_HISTORY_MESSAGES_FOR_LLM
from app.engine.scheduler import Scheduler
from app.engine.state import (
    ConversationHistory,
    ConversationMessage,
    ConversationState,
    DataKey,
)
from app.engine.tools import (
    StateData,
    _get_state,
    _set_state,
    get_or_create_user_profile,
)
from app.schemas.router import RouteDecision

logger = logging.getLogger(__name__)

# History limits matching legacy §3.3
MAX_HISTORY_LENGTH = 50


def process_turn(
    state_data: StateData,
    participant_id: str,
    user_message: str,
    llm: BaseChatModel | None = None,
    router_llm: BaseChatModel | None = None,
    scheduler: Scheduler | None = None,
) -> tuple[str, RouteDecision]:
    """Process one user turn through the LangChain orchestrator.

    Parameters
    ----------
    state_data:
        Mutable dict[str, str] holding engine state.
    participant_id:
        Stable user identity (h4ckath0n user id).
    user_message:
        Raw text from the user.
    llm:
        Chat model for the specialist agents. If ``None``, a stub is used.
    router_llm:
        Chat model for the router. If ``None``, deterministic routing is used.
    scheduler:
        Scheduler instance. Created on demand if ``None``.

    Returns
    -------
    (assistant_text, route_decision)
    """
    sched = scheduler or Scheduler()

    # -- Step 0: History management ------------------------------------------
    history = _load_history(state_data)
    now = datetime.now(timezone.utc)

    # Append user message
    history.messages.append(
        ConversationMessage(role="user", content=user_message, timestamp=now)
    )

    # Handle poll responses (Done, more/less/same) — same as legacy flow.py
    _handle_poll_responses(state_data, user_message)

    # Cancel pending reminders on reply (§5.2)
    sched.handle_daily_prompt_reply(state_data, participant_id, reply_timestamp=now)

    # -- Step 1: Compute state summary for router ----------------------------
    sub_state = _get_sub_state(state_data)
    profile = get_or_create_user_profile(state_data)
    profile_summary = (
        f"PromptAnchor={'set' if profile.prompt_anchor else 'missing'}, "
        f"PreferredTime={'set' if profile.preferred_time else 'missing'}, "
        f"HabitDomain={'set' if profile.habit_domain else 'missing'}"
    )

    # -- Step 2: Route -------------------------------------------------------
    decision = route_turn(
        user_text=user_message,
        sub_state=sub_state,
        profile_summary=profile_summary,
        llm=router_llm,
    )
    logger.info("Route decision: %s", decision.route)

    # -- Step 3: Invoke specialist -------------------------------------------
    chat_history_msgs = _to_langchain_messages(history, MAX_HISTORY_MESSAGES_FOR_LLM)

    if decision.route == "FEEDBACK":
        if llm is not None:
            agent = create_feedback_agent(llm, state_data)
            assistant_text = run_feedback(agent, user_message, chat_history_msgs)
        else:
            # Fallback to legacy module when no LLM is available
            from app.engine.modules import FeedbackModule, StubLLMClient

            mod = FeedbackModule(llm_client=StubLLMClient())
            trimmed = history.messages[-MAX_HISTORY_MESSAGES_FOR_LLM:]
            assistant_text = mod.execute(state_data, user_message, trimmed)
        # Cancel pending feedback timers (§4.3)
        _set_state(state_data, DataKey.FEEDBACK_TIMER_ID, "")
        _set_state(state_data, DataKey.FEEDBACK_FOLLOWUP_TIMER_ID, "")
    else:
        if llm is not None:
            agent = create_intake_agent(llm, state_data)
            assistant_text = run_intake(agent, user_message, chat_history_msgs)
        else:
            from app.engine.modules import IntakeModule, StubLLMClient

            mod = IntakeModule(llm_client=StubLLMClient())
            trimmed = history.messages[-MAX_HISTORY_MESSAGES_FOR_LLM:]
            assistant_text = mod.execute(state_data, user_message, trimmed)

    # -- Step 4: Persist history ---------------------------------------------
    history.messages.append(
        ConversationMessage(
            role="assistant",
            content=assistant_text,
            timestamp=datetime.now(timezone.utc),
        )
    )
    _save_history(state_data, history)

    return assistant_text, decision


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_sub_state(state_data: StateData) -> str:
    """Return the current sub-state string, defaulting to INTAKE."""
    raw = _get_state(state_data, DataKey.CONVERSATION_STATE, "")
    if raw == ConversationState.FEEDBACK.value:
        return "FEEDBACK"
    return "INTAKE"


def _handle_poll_responses(state_data: StateData, user_message: str) -> None:
    """Handle Done / intensity poll responses (legacy flow.py logic)."""
    text = user_message.strip().lower()

    if text == "done":
        profile = get_or_create_user_profile(state_data)
        profile.success_count += 1
        _set_state(state_data, DataKey.USER_PROFILE, profile.model_dump_json())

    if text in ("more", "less", "same"):
        profile = get_or_create_user_profile(state_data)
        mapping = {"more": "high", "less": "low", "same": "normal"}
        profile.intensity = mapping.get(text, profile.intensity)
        _set_state(state_data, DataKey.USER_PROFILE, profile.model_dump_json())


def _load_history(state_data: StateData) -> ConversationHistory:
    raw = _get_state(state_data, DataKey.CONVERSATION_HISTORY, "")
    if raw:
        try:
            return ConversationHistory.model_validate_json(raw)
        except Exception:
            pass
    return ConversationHistory()


def _save_history(state_data: StateData, history: ConversationHistory) -> None:
    if len(history.messages) > MAX_HISTORY_LENGTH:
        history.messages = history.messages[-MAX_HISTORY_LENGTH:]
    _set_state(state_data, DataKey.CONVERSATION_HISTORY, history.model_dump_json())


def _to_langchain_messages(
    history: ConversationHistory,
    max_messages: int,
) -> list[HumanMessage | AIMessage]:
    """Convert conversation history to LangChain message objects."""
    trimmed = history.messages[-max_messages:]
    result: list[HumanMessage | AIMessage] = []
    for msg in trimmed:
        if msg.role == "user":
            result.append(HumanMessage(content=msg.content))
        elif msg.role == "assistant":
            result.append(AIMessage(content=msg.content))
    return result
