"""New architecture turn engine — Router + specialist agents with proposal/commit flow.

Implements the turn pipeline:
1. Persist user message
2. Load UserProfile + Memory + recent history
3. Router decides which specialist to run
4. Invoke specialist agent (Intake, Feedback, or Coach)
5. Collect patch proposals made during the agent run
6. Router validates proposals and commits approved ones
7. Persist assistant message
8. Return results for SSE emission
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime, timedelta

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.proposals import _process_proposals
from app.agents.routing import (
    ROUTER_SYSTEM_PROMPT,
    _get_active_condition_context,
    _get_randomization_key,
    route_turn_deterministic,
    route_turn_llm,
)
from app.agents.specialists import (
    _build_memory_summary,
    _build_profile_summary,
    _create_specialist_agent,
    _run_specialist_stub,
    _strip_feedback_plan_line,
)
from app.models import (
    Conversation,
    ConversationRuntimeState,
    DailyInterventionLog,
    Message,
    Participation,
)
from app.schemas.messaging import DebugInfo
from app.schemas.router import RouteDecision
from app.services.intervention_config import get_static_intervention
from app.services.profile_service import load_memory_items, load_user_profile
from app.tools.proposal_tools import ProposalCollector

logger = logging.getLogger(__name__)

# Re-exported so tests can import these from `app.agents.engine` and so that
# `process_turn` resolves them by bare name (allowing monkeypatching of e.g.
# `engine_mod._get_active_condition_context`).
__all__ = [
    "ROUTER_SYSTEM_PROMPT",
    "_build_memory_summary",
    "_build_profile_summary",
    "_create_specialist_agent",
    "_get_active_condition_context",
    "_get_randomization_key",
    "_process_proposals",
    "_run_specialist_stub",
    "_strip_feedback_plan_line",
    "process_turn",
    "route_turn_deterministic",
    "route_turn_llm",
]

MAX_HISTORY_MESSAGES = 30
CONDITION_C_EXCLUDED_SOURCES = ["COND_B", "COND_D"]


# ---------------------------------------------------------------------------
# Main turn pipeline
# ---------------------------------------------------------------------------


async def process_turn(
    db: AsyncSession,
    conversation: Conversation,
    membership_id: int,
    user_msg: Message | None,
    user_text: str,
    llm: BaseChatModel | None = None,
    router_llm: BaseChatModel | None = None,
    on_token: Callable[[str], Coroutine[None, None, None]] | None = None,
) -> tuple[str, RouteDecision, DebugInfo, int | None]:
    """Process one user turn through the new Router + specialist architecture.

    Returns (assistant_text, route_decision, debug_info, participation_id).
    """
    # Step 1: Load profile + memory + recent history
    profile = await load_user_profile(db, membership_id)
    memory_items = await load_memory_items(db, membership_id)

    # Build unified prompt context (display_name + time) once for all LLM paths
    from app.services.prompt_context import get_prompt_context_for_membership

    prompt_args = await get_prompt_context_for_membership(db, membership_id)

    # Load recent messages for context
    (
        current_condition,
        participation,
        study_day_index,
    ) = await _get_active_condition_context(
        db=db,
        membership_id=membership_id,
        current_date=datetime.now(UTC).date(),
    )
    prompt_args["active_condition"] = current_condition or "NONE"
    history_query = select(Message).where(Message.conversation_id == conversation.id)
    if current_condition == "C":
        # Anti-contamination: never let Condition C see messages produced under
        # Conditions B or D (which contain explicit If/Then framing) and
        # restrict history to the trailing 24h so longer-term drift cannot
        # leak framing back into the LLM's context window.
        history_query = history_query.where(
            Message.condition_source.notin_(CONDITION_C_EXCLUDED_SOURCES)
        )
        window_start = datetime.now(UTC) - timedelta(hours=24)
        history_query = history_query.where(Message.created_at >= window_start)

    result = await db.execute(
        history_query.order_by(Message.id.desc()).limit(MAX_HISTORY_MESSAGES)
    )
    recent_msgs = list(reversed(result.scalars().all()))
    recent_message_ids = [m.id for m in recent_msgs]

    # Read conversation state from runtime state if available
    state_result = await db.execute(
        select(ConversationRuntimeState).where(
            ConversationRuntimeState.conversation_id == conversation.id
        )
    )
    conv_state = ""
    if runtime_state := state_result.scalar_one_or_none():
        try:
            state_data = json.loads(runtime_state.state_json)
            conv_state = state_data.get("conversationState", "")
        except (json.JSONDecodeError, TypeError):
            pass

    # Step 2: Route
    if router_llm is not None:
        profile_summary = _build_profile_summary(profile)
        memory_summary = _build_memory_summary(memory_items)
        decision = route_turn_llm(
            router_llm,
            profile_summary,
            memory_summary,
            conv_state,
            user_text,
            time_context=prompt_args,
        )
    else:
        decision = route_turn_deterministic(profile, conv_state)

    logger.info("Route decision: %s (reason: %s)", decision.route, decision.reason)

    # Auto-enrollment: create Participation when the user is past INTAKE
    if decision.route != "INTAKE" and participation is None:
        participation = Participation(
            membership_id=membership_id,
            study_id="microcoach_v1",
            study_start_date=datetime.now(UTC),
            timezone=getattr(profile, "timezone", "UTC"),
        )
        db.add(participation)
        await db.flush()
        # Recalculate condition now that a Participation record exists.
        # If the randomization salt is not configured (e.g. in tests) we keep
        # the previous None values rather than crashing.
        try:
            (
                current_condition,
                participation,
                study_day_index,
            ) = await _get_active_condition_context(
                db=db,
                membership_id=membership_id,
                current_date=datetime.now(UTC).date(),
            )
            prompt_args["active_condition"] = current_condition or "NONE"
        except RuntimeError:
            logger.warning(
                "Could not determine condition after auto-enrollment "
                "(FLOW_CRYPTO_MASTER_KEY not configured)"
            )

    # Daily-log heartbeat: ensure a DailyInterventionLog exists for today
    if participation is not None and current_condition is not None:
        today = datetime.now(UTC).date()
        log_result = await db.execute(
            select(DailyInterventionLog).where(
                DailyInterventionLog.participation_id == participation.id,
                DailyInterventionLog.intervention_date == today,
            )
        )
        if log_result.scalar_one_or_none() is None:
            log = DailyInterventionLog(
                participation_id=participation.id,
                intervention_date=today,
                study_day_index=study_day_index,
                assigned_condition=current_condition,
                extracted_state={},
            )
            db.add(log)
            await db.flush()

    # Link user message to participation
    if user_msg is not None and participation is not None:
        user_msg.participation_id = participation.id

    # Step 2.5: For Conditions C and D, ensure the cross-condition
    # sterilized memory is up to date and inject the latest summary as a
    # SystemMessage at the head of the chat history. This is the "semantic
    # firewall" — both conditions read the same clinical summary so
    # Condition C never sees Condition D's framing while still keeping
    # multi-day memory.
    daily_summary_text: str | None = None
    if participation is not None and current_condition in {"C", "D"}:
        try:
            from app.services.eod_summarizer import (
                ensure_summaries_up_to,
                load_latest_summary,
            )

            yesterday = datetime.now(UTC).date() - timedelta(days=1)
            await ensure_summaries_up_to(db, participation, yesterday)
            daily_summary_text = await load_latest_summary(db, participation.id)
        except Exception:
            logger.exception(
                "Failed to ensure/load EOD summary for participation %s",
                participation.id,
            )

    # Collect tool names for debugging
    tool_names = []

    # Step 3: Invoke specialist
    if llm is not None:
        # LLM-backed agent invocation
        collector = ProposalCollector()
        from app.tools.proposal_tools import make_proposal_tools

        proposal_tools = make_proposal_tools(collector, source_bot=decision.route)

        # Add scheduler tools for COACH and INTAKE
        if decision.route in ("COACH", "INTAKE"):
            from app.tools.scheduler_tools import make_scoped_list_schedules_tool

            proposal_tools.append(make_scoped_list_schedules_tool(membership_id))

        # Collect tool names for debug info
        tool_names = [t.name for t in proposal_tools]

        chat_history: list[HumanMessage | AIMessage | SystemMessage] = []
        # When creating history, exclude the just-added user message (which is last)
        # IF user_msg is present. If user_msg is None (system trigger), use all history.
        if daily_summary_text:
            chat_history.append(
                SystemMessage(
                    content=(
                        "Sterilized cross-day memory (clinical, no framing) — "
                        "use this for continuity but do not quote or imitate its "
                        f"style:\n{daily_summary_text}"
                    )
                )
            )
        history_msgs = recent_msgs[:-1] if user_msg else recent_msgs
        for msg in history_msgs:
            if msg.role == "user":
                chat_history.append(HumanMessage(content=msg.content))
            elif msg.role == "assistant":
                chat_history.append(AIMessage(content=msg.content))

        if decision.route == "INTAKE":
            from app.agents.intake import run_intake

            assistant_text, tool_calls = await run_intake(
                _create_specialist_agent(
                    llm, proposal_tools, "intake_system", prompt_args
                ),
                user_text,
                chat_history,
                on_token=on_token,
            )
        elif decision.route == "FEEDBACK":
            if current_condition in {"A", "B"}:
                # Experimental control: in conditions A and B the feedback
                # path must NOT touch the LLM (and must not propose any
                # profile/memory patches). Run the deterministic script.
                from app.services.feedback_script import run_static_feedback

                assistant_text = await run_static_feedback(
                    db, membership_id, user_text, current_condition
                )
                tool_calls = []
                decision = RouteDecision(
                    route="STATIC_FEEDBACK",
                    reason=f"static feedback script for condition {current_condition}",
                )
            else:
                from app.agents.feedback import run_feedback

                assistant_text, tool_calls = await run_feedback(
                    _create_specialist_agent(
                        llm, proposal_tools, "feedback_system", prompt_args
                    ),
                    user_text,
                    chat_history,
                    on_token=on_token,
                )
                assistant_text = _strip_feedback_plan_line(assistant_text)
        elif (
            current_condition in {"A", "B"}
            and participation is not None
            and study_day_index is not None
        ):
            assistant_text = get_static_intervention(
                current_condition,
                participation.id,
                study_day_index,
            )
            tool_calls = []
            decision = RouteDecision(
                route="STATIC_TEMPLATE",
                reason=f"static template for condition {current_condition}",
            )
        else:
            from app.agents.coach import run_coach

            assistant_text, tool_calls = await run_coach(
                _create_specialist_agent(
                    llm, proposal_tools, "coach_system", prompt_args
                ),
                user_text,
                chat_history,
                active_condition=current_condition,
                on_token=on_token,
            )
    else:
        # Stub mode (no LLM)
        if decision.route == "FEEDBACK" and current_condition in {"A", "B"}:
            from app.services.feedback_script import run_static_feedback

            assistant_text = await run_static_feedback(
                db, membership_id, user_text, current_condition
            )
            collector = ProposalCollector()
            tool_names = []
            tool_calls = []
            decision = RouteDecision(
                route="STATIC_FEEDBACK",
                reason=f"static feedback script for condition {current_condition}",
            )
        elif (
            current_condition in {"A", "B"}
            and participation is not None
            and study_day_index is not None
        ):
            assistant_text = get_static_intervention(
                current_condition,
                participation.id,
                study_day_index,
            )
            collector = ProposalCollector()
            tool_names = []
            tool_calls = []
            decision = RouteDecision(
                route="STATIC_TEMPLATE",
                reason=f"static template for condition {current_condition}",
            )
        else:
            assistant_text, collector = _run_specialist_stub(decision.route, user_text)
            tool_names = ["stub_tools"]  # simplified for stub
            tool_calls = []

    # Step 4: Process proposals through Router validator
    await _process_proposals(
        db,
        membership_id,
        profile,
        collector,
        recent_message_ids,
        latest_user_message_id=user_msg.id if user_msg else None,
    )

    is_static_template = decision.route in {"STATIC_TEMPLATE", "STATIC_FEEDBACK"}
    debug_info = DebugInfo(
        agent=decision.route if not is_static_template else "STATIC_TEMPLATE",
        condition=current_condition or "NONE",
        prompt_args=prompt_args,
        tools=tool_names if not is_static_template else [],
        tool_calls=tool_calls if not is_static_template else [],
    )

    return (
        assistant_text,
        decision,
        debug_info,
        participation.id if participation else None,
    )
