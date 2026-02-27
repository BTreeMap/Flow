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
from datetime import datetime, timezone

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Conversation, ConversationRuntimeState, Message
from app.prompt_loader import load_prompt
from app.schemas.patches import (
    FEEDBACK_ALLOWED_FIELDS,
    INTAKE_ALLOWED_FIELDS,
    MemoryItemData,
    MemoryPatchProposal,
    ProfilePatchProposal,
    SchedulePatchProposal,
    UserProfileData,
)
from app.schemas.router import RouteDecision
from app.services.profile_service import (
    add_memory_item,
    apply_profile_patch,
    load_memory_items,
    load_user_profile,
    log_patch_audit,
    save_user_profile,
    validate_memory_patch,
    validate_profile_patch,
)
from app.services.scheduler_service import create_nudge_schedule, deactivate_schedule
from app.tools.proposal_tools import ProposalCollector

logger = logging.getLogger(__name__)

MAX_HISTORY_MESSAGES = 30

# ---------------------------------------------------------------------------
# Router (structured output, no user-visible text)
# ---------------------------------------------------------------------------

ROUTER_SYSTEM_PROMPT = load_prompt("router_system")

_router_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", ROUTER_SYSTEM_PROMPT),
        (
            "human",
            "Profile summary: {profile_summary}\n"
            "Memory summary: {memory_summary}\n"
            "Conversation state: {conv_state}\n"
            "User message: {user_text}\n"
            "Return the route.",
        ),
    ]
)


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
) -> RouteDecision:
    """Use LLM with structured output for routing."""
    # Pass schema dict to get a dict back, avoiding Pydantic serialization issues in LangChain
    structured = llm.with_structured_output(RouteDecision.model_json_schema())
    try:
        result = (_router_prompt | structured).invoke(
            {
                "profile_summary": profile_summary,
                "memory_summary": memory_summary,
                "conv_state": conv_state,
                "user_text": user_text,
            }
        )
    except Exception:
        logger.exception("Router LLM invocation failed")
        return RouteDecision(route="COACH", reason="LLM invocation failed")

    if isinstance(result, dict):
        try:
            return RouteDecision.model_validate(result)
        except Exception:
            logger.warning("Failed to parse RouteDecision from dict: %s", result)

    if isinstance(result, RouteDecision):
        return result

    return RouteDecision(route="COACH", reason="LLM fallback")


# ---------------------------------------------------------------------------
# Specialist invocation (stub mode for when no LLM is available)
# ---------------------------------------------------------------------------


def _run_specialist_stub(route: str, user_text: str) -> tuple[str, ProposalCollector]:
    """Stub specialist invocation for testing without LLM."""
    collector = ProposalCollector()
    if route == "INTAKE":
        text = (
            "I'm here to help you set up your habit-building routine. "
            "Could you tell me more about the habit you'd like to work on?"
        )
    elif route == "FEEDBACK":
        text = (
            "I'd love to hear how things went with your habit today. "
            "Feel free to share any updates!"
        )
    else:
        text = "I'm here to support your habit journey. How can I help you today?"
    return text, collector


def _build_profile_summary(profile: UserProfileData) -> str:
    """Build a summary string for the router."""
    return (
        f"PromptAnchor={'set' if profile.prompt_anchor else 'missing'}, "
        f"PreferredTime={'set' if profile.preferred_time else 'missing'}, "
        f"HabitDomain={'set' if profile.habit_domain else 'missing'}, "
        f"Intensity={profile.intensity}"
    )


def _build_memory_summary(items: list[MemoryItemData]) -> str:
    """Build a summary string from memory items."""
    if not items:
        return "No memory items yet."
    summaries = [item.content[:100] for item in items[-5:]]
    return "; ".join(summaries)


# ---------------------------------------------------------------------------
# Router commit logic
# ---------------------------------------------------------------------------


async def _process_proposals(
    db: AsyncSession,
    membership_id: int,
    profile: UserProfileData,
    collector: ProposalCollector,
    recent_message_ids: list[int],
    latest_user_message_id: int | None = None,
) -> UserProfileData:
    """Validate and commit proposals from the specialist. Returns updated profile."""
    now = datetime.now(timezone.utc)
    profile_changed = False

    # Process profile proposals
    for raw in collector.profile_proposals:
        try:
            if latest_user_message_id and isinstance(raw, dict):
                evidence = raw.get("evidence", {})
                message_ids = (
                    evidence.get("message_ids", [])
                    if isinstance(evidence, dict)
                    else []
                )
                patch = raw.get("patch", {})
                source_bot = raw.get("source_bot")
                allowed_fields = (
                    INTAKE_ALLOWED_FIELDS
                    if source_bot == "INTAKE"
                    else FEEDBACK_ALLOWED_FIELDS
                    if source_bot == "FEEDBACK"
                    else set()
                )
                if (
                    not message_ids
                    and isinstance(patch, dict)
                    and set(patch).issubset(allowed_fields)
                ):
                    raw["evidence"] = {
                        "message_ids": [latest_user_message_id],
                        "quotes": evidence.get("quotes", [])
                        if isinstance(evidence, dict)
                        else [],
                    }
            try:
                proposal = ProfilePatchProposal.model_validate(raw)
            except Exception:
                logger.warning("Invalid profile proposal: %s", raw)
                continue

            valid, reason = validate_profile_patch(proposal, recent_message_ids)

            await log_patch_audit(
                db=db,
                membership_id=membership_id,
                proposal_type="profile",
                source_bot=proposal.source_bot,
                patch_json=json.dumps(proposal.patch),
                confidence=proposal.confidence,
                evidence_json=proposal.evidence.model_dump_json(),
                decision="committed" if valid else f"ignored: {reason}",
                committed_at=now if valid else None,
                flush=False,
            )

            if valid:
                profile = apply_profile_patch(profile, proposal.patch)
                profile_changed = True
                logger.info("Committed profile patch from %s", proposal.source_bot)
        except Exception:
            logger.exception("Failed to process profile proposal: %s", raw)

    # Process memory proposals
    for raw in collector.memory_proposals:
        try:
            if latest_user_message_id and isinstance(raw, dict):
                evidence = raw.get("evidence", {})
                message_ids = (
                    evidence.get("message_ids", [])
                    if isinstance(evidence, dict)
                    else []
                )
                source_bot = raw.get("source_bot")
                if not message_ids and source_bot in {"INTAKE", "FEEDBACK"}:
                    raw["evidence"] = {
                        "message_ids": [latest_user_message_id],
                        "quotes": evidence.get("quotes", [])
                        if isinstance(evidence, dict)
                        else [],
                    }
            try:
                proposal = MemoryPatchProposal.model_validate(raw)
            except Exception:
                logger.warning("Invalid memory proposal: %s", raw)
                continue

            valid, reason = validate_memory_patch(proposal, recent_message_ids)

            await log_patch_audit(
                db=db,
                membership_id=membership_id,
                proposal_type="memory",
                source_bot=proposal.source_bot,
                patch_json=json.dumps(
                    [i.model_dump(mode="json") for i in proposal.items]
                ),
                confidence=proposal.confidence,
                evidence_json=proposal.evidence.model_dump_json(),
                decision="committed" if valid else f"ignored: {reason}",
                committed_at=now if valid else None,
                flush=False,
            )

            if valid:
                for item in proposal.items:
                    await add_memory_item(db, membership_id, item, flush=False)
                logger.info(
                    "Committed %d memory items from %s",
                    len(proposal.items),
                    proposal.source_bot,
                )
        except Exception:
            logger.exception("Failed to process memory proposal: %s", raw)

    # Process schedule proposals
    for raw in collector.schedule_proposals:
        try:
            if latest_user_message_id and isinstance(raw, dict):
                evidence = raw.get("evidence", {})
                message_ids = (
                    evidence.get("message_ids", [])
                    if isinstance(evidence, dict)
                    else []
                )
                if not message_ids:
                    raw["evidence"] = {
                        "message_ids": [latest_user_message_id],
                        "quotes": evidence.get("quotes", [])
                        if isinstance(evidence, dict)
                        else [],
                    }
            try:
                proposal = SchedulePatchProposal.model_validate(raw)
            except Exception:
                logger.warning("Invalid schedule proposal: %s", raw)
                continue

            # Validate schedule proposal (basic checks for now)
            valid = True
            reason = ""
            if proposal.action == "create":
                if not proposal.topic or not proposal.time:
                    valid = False
                    reason = "Missing topic or time"
            elif proposal.action == "delete":
                if not proposal.schedule_id:
                    valid = False
                    reason = "Missing schedule_id"

            if valid and proposal.source_bot != "COACH":
                # Assuming only Coach should really be messing with schedules for now,
                # or at least that's where we exposed the tools.
                # But technically any bot could if we let it.
                # Let's keep it open but log it.
                pass

            await log_patch_audit(
                db=db,
                membership_id=membership_id,
                proposal_type="schedule",
                source_bot=proposal.source_bot,
                patch_json=json.dumps(
                    {
                        "action": proposal.action,
                        "topic": proposal.topic,
                        "time": proposal.time,
                        "schedule_id": proposal.schedule_id,
                    }
                ),
                confidence=proposal.confidence,
                evidence_json=proposal.evidence.model_dump_json(),
                decision="committed" if valid else f"ignored: {reason}",
                committed_at=now if valid else None,
                flush=False,
            )

            if valid:
                if proposal.action == "create":
                    await create_nudge_schedule(
                        db, membership_id, proposal.topic, proposal.time
                    )
                    logger.info(
                        "Committed schedule creation from %s", proposal.source_bot
                    )
                elif proposal.action == "delete":
                    await deactivate_schedule(db, proposal.schedule_id)
                    logger.info(
                        "Committed schedule deletion from %s", proposal.source_bot
                    )

        except Exception:
            logger.exception("Failed to process schedule proposal: %s", raw)

    if profile_changed:
        await save_user_profile(db, membership_id, profile, flush=False)

    # Final flush for all changes (audit logs, memory items, profile updates, schedules)
    await db.flush()

    return profile


# ---------------------------------------------------------------------------
# Specialist agent factory
# ---------------------------------------------------------------------------

_RECURSION_LIMIT = 22


def _create_specialist_agent(
    llm: BaseChatModel,
    tools: list,
    prompt_name: str,
    prompt_args: dict[str, str] | None = None,
) -> object:
    """Build a LangGraph agent for a specialist using a prompt loaded from file."""
    from langgraph.prebuilt import create_react_agent

    text = load_prompt(prompt_name)
    if prompt_args:
        try:
            text = text.format(**prompt_args)
        except KeyError:
            pass  # Prompt might not use all args, or args might be missing

    return create_react_agent(llm, tools=tools, prompt=text)


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
) -> tuple[str, RouteDecision, dict]:
    """Process one user turn through the new Router + specialist architecture.

    Returns (assistant_text, route_decision, debug_info).
    """
    # Step 1: Load profile + memory + recent history
    profile = await load_user_profile(db, membership_id)
    memory_items = await load_memory_items(db, membership_id)

    # Load recent messages for context
    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.id.desc())
        .limit(MAX_HISTORY_MESSAGES)
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
            router_llm, profile_summary, memory_summary, conv_state, user_text
        )
    else:
        decision = route_turn_deterministic(profile, conv_state)

    logger.info("Route decision: %s (reason: %s)", decision.route, decision.reason)

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
            from app.tools.scheduler_tools import list_schedules

            proposal_tools.append(list_schedules)

        # Collect tool names for debug info
        tool_names = [t.name for t in proposal_tools]

        chat_history: list[HumanMessage | AIMessage] = []
        # When creating history, exclude the just-added user message (which is last)
        # IF user_msg is present. If user_msg is None (system trigger), use all history.
        history_msgs = recent_msgs[:-1] if user_msg else recent_msgs
        for msg in history_msgs:
            if msg.role == "user":
                chat_history.append(HumanMessage(content=msg.content))
            elif msg.role == "assistant":
                chat_history.append(AIMessage(content=msg.content))

        prompt_args = {"display_name": profile.display_name or "there"}

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
            from app.agents.feedback import run_feedback

            assistant_text, tool_calls = await run_feedback(
                _create_specialist_agent(
                    llm, proposal_tools, "feedback_system", prompt_args
                ),
                user_text,
                chat_history,
                on_token=on_token,
            )
        else:
            from app.agents.coach import run_coach

            assistant_text, tool_calls = await run_coach(
                _create_specialist_agent(
                    llm, proposal_tools, "coach_system", prompt_args
                ),
                user_text,
                chat_history,
                on_token=on_token,
            )
    else:
        # Stub mode (no LLM)
        assistant_text, collector = _run_specialist_stub(decision.route, user_text)
        tool_names = ["stub_tools"]  # simplified for stub
        tool_calls: list[dict] = []

    # Step 4: Process proposals through Router validator
    await _process_proposals(
        db,
        membership_id,
        profile,
        collector,
        recent_message_ids,
        latest_user_message_id=user_msg.id if user_msg else None,
    )

    debug_info = {
        "agent": decision.route,
        "tools": tool_names,
        "tool_calls": tool_calls,
    }

    return assistant_text, decision, debug_info
