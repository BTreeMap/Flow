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
import os
import string
from collections.abc import Callable, Coroutine
from datetime import date, datetime, timezone
from functools import lru_cache

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Conversation,
    ConversationRuntimeState,
    DailyInterventionLog,
    Message,
    Participation,
    ScheduledTask,
)
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
from app.models import NotificationRule, NotificationRuleState
from app.services.intervention_config import get_static_intervention
from app.services.notification_engine import compute_next_due_utc, get_user_timezone
from app.services.randomization import get_daily_condition
from app.tools.proposal_tools import ProposalCollector

logger = logging.getLogger(__name__)

MAX_HISTORY_MESSAGES = 30
CONDITION_C_EXCLUDED_SOURCES = ["COND_B", "COND_D"]

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


@lru_cache(maxsize=1)
def _get_randomization_salt() -> str:
    salt = os.environ.get("FLOW_RANDOMIZATION_SALT")
    if not salt:
        raise RuntimeError(
            "FLOW_RANDOMIZATION_SALT must be set for participation randomization"
        )
    if len(salt) < 32:
        raise RuntimeError(
            "FLOW_RANDOMIZATION_SALT must be at least 32 characters for experimental integrity"
        )
    return salt


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

    salt = _get_randomization_salt()
    condition = get_daily_condition(
        participation_id=participation.id,
        study_start_date=participation.study_start_date,
        current_date=current_date,
        salt=salt,
    )
    return condition, participation, study_day_index


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
                if not proposal.rule_id:
                    valid = False
                    reason = "Missing rule_id"

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
                        "rule_id": proposal.rule_id,
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
                    rule = NotificationRule(
                        membership_id=membership_id,
                        kind="daily_local_time",
                        config_json=json.dumps(
                            {"topic": proposal.topic, "time": proposal.time}
                        ),
                        tz_policy="floating_user_tz",
                        is_active=True,
                    )
                    db.add(rule)
                    await db.flush()
                    user_tz = await get_user_timezone(db, membership_id)
                    next_due = compute_next_due_utc(rule, user_tz)
                    state = NotificationRuleState(
                        rule_id=rule.id,
                        next_due_at_utc=next_due,
                    )
                    db.add(state)
                    logger.info(
                        "Committed schedule creation from %s", proposal.source_bot
                    )
                elif proposal.action == "delete":
                    rule_result = await db.execute(
                        select(NotificationRule).where(
                            NotificationRule.id == proposal.rule_id,
                            NotificationRule.membership_id == membership_id,
                        )
                    )
                    rule = rule_result.scalar_one_or_none()
                    if rule:
                        rule.is_active = False
                        await db.execute(
                            update(ScheduledTask)
                            .where(
                                ScheduledTask.rule_id == rule.id,
                                ScheduledTask.status == "pending",
                            )
                            .values(status="cancelled")
                        )
                        logger.info(
                            "Committed schedule deletion from %s",
                            proposal.source_bot,
                        )
                    else:
                        logger.warning(
                            "Ignored schedule deletion from %s: "
                            "rule_id=%s not found for membership_id=%s "
                            "(out-of-scope or missing)",
                            proposal.source_bot,
                            proposal.rule_id,
                            membership_id,
                        )

        except Exception:
            logger.exception("Failed to process schedule proposal: %s", raw)

    # Process telemetry proposals (FEEDBACK bot only)
    for proposal in collector.telemetry_proposals:
        try:
            today = datetime.now(timezone.utc).date()
            log_result = await db.execute(
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
            log = log_result.scalar_one_or_none()
            if log is not None:
                log.extracted_state = {
                    **(log.extracted_state or {}),
                    **proposal.get("state_updates", {}),
                }
                db.add(log)
        except Exception:
            logger.exception("Failed to process telemetry proposal: %s", proposal)

    if profile_changed:
        await save_user_profile(db, membership_id, profile, flush=False)

    # Final flush for all changes (audit logs, memory items, profile updates, schedules)
    await db.flush()

    return profile


# ---------------------------------------------------------------------------
# Specialist agent factory
# ---------------------------------------------------------------------------

_RECURSION_LIMIT = 22


class _SafeDict(dict):
    """Dict subclass that returns '{key}' for missing keys instead of raising."""

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


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
        # Use string.Template to safely interpolate $variables while ignoring {} braces
        text = string.Template(text).safe_substitute(prompt_args)

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
) -> tuple[str, RouteDecision, dict, int | None]:
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
        current_date=datetime.now(timezone.utc).date(),
    )
    prompt_args["active_condition"] = current_condition or "NONE"
    history_query = select(Message).where(Message.conversation_id == conversation.id)
    if current_condition == "C":
        history_query = history_query.where(
            Message.condition_source.notin_(CONDITION_C_EXCLUDED_SOURCES)
        )

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
            study_start_date=datetime.now(timezone.utc),
            timezone="UTC",
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
                current_date=datetime.now(timezone.utc).date(),
            )
            prompt_args["active_condition"] = current_condition or "NONE"
        except RuntimeError:
            logger.warning(
                "Could not determine condition after auto-enrollment "
                "(FLOW_RANDOMIZATION_SALT not configured)"
            )

    # Daily-log heartbeat: ensure a DailyInterventionLog exists for today
    if participation is not None and current_condition is not None:
        today = datetime.now(timezone.utc).date()
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
                study_day_index=study_day_index or 0,
                assigned_condition=current_condition,
                extracted_state={},
            )
            db.add(log)
            await db.flush()

    # Link user message to participation
    if user_msg is not None and participation is not None:
        user_msg.participation_id = participation.id

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

        chat_history: list[HumanMessage | AIMessage] = []
        # When creating history, exclude the just-added user message (which is last)
        # IF user_msg is present. If user_msg is None (system trigger), use all history.
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
            from app.agents.feedback import run_feedback

            assistant_text, tool_calls = await run_feedback(
                _create_specialist_agent(
                    llm, proposal_tools, "feedback_system", prompt_args
                ),
                user_text,
                chat_history,
                on_token=on_token,
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
        if (
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

    is_static_template = current_condition in {"A", "B"}
    debug_info = {
        "agent": decision.route if not is_static_template else "STATIC_TEMPLATE",
        "condition": current_condition or "NONE",
        "prompt_args": prompt_args,
        "tools": tool_names if not is_static_template else [],
        "tool_calls": tool_calls if not is_static_template else [],
    }

    return (
        assistant_text,
        decision,
        debug_info,
        participation.id if participation else None,
    )
