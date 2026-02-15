"""Tool definitions and execution matching legacy §4.4–§4.7, §8.1."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel

from app.engine.state import (
    ConversationState,
    DataKey,
    ScheduleInfo,
    UserProfile,
)
from app.engine.tone import update_profile_tone, validate_proposal


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

StateData = dict[str, str]


def _get_state(state_data: StateData, key: DataKey, default: str = "") -> str:
    return state_data.get(key.value, default)


def _set_state(state_data: StateData, key: DataKey, value: str) -> None:
    state_data[key.value] = value


def get_or_create_user_profile(state_data: StateData) -> UserProfile:
    """Retrieve or create default profile with Intensity='normal' (§4.7)."""
    raw = _get_state(state_data, DataKey.USER_PROFILE)
    if raw:
        return UserProfile.model_validate_json(raw)
    profile = UserProfile(intensity="normal")
    _set_state(state_data, DataKey.USER_PROFILE, profile.model_dump_json())
    return profile


def _save_user_profile(state_data: StateData, profile: UserProfile) -> None:
    _set_state(state_data, DataKey.USER_PROFILE, profile.model_dump_json())


# ---------------------------------------------------------------------------
# Tool result helpers — errors are informational strings, never exceptions (§8.1)
# ---------------------------------------------------------------------------


class ToolResult(BaseModel):
    tool_call_id: str = ""
    name: str = ""
    result: str = ""


class ToolCall(BaseModel):
    id: str = ""
    name: str = ""
    arguments: dict[str, Any] = {}


# ---------------------------------------------------------------------------
# ProfileSaveTool (§4.7)
# ---------------------------------------------------------------------------

_PROFILE_FIELDS = [
    "prompt_anchor",
    "preferred_time",
    "habit_domain",
    "motivational_frame",
    "additional_info",
    "last_successful_prompt",
    "last_barrier",
    "last_motivator",
    "last_tweak",
]


def execute_profile_save(
    state_data: StateData,
    arguments: dict[str, Any],
) -> str:
    """Field-by-field merge with tone proposal handling (§4.7).

    Returns 'success' or 'noop'.
    """
    profile = get_or_create_user_profile(state_data)
    changed = False

    # Legacy alias: last_blocker → last_barrier
    if "last_blocker" in arguments and "last_barrier" not in arguments:
        arguments["last_barrier"] = arguments.pop("last_blocker")

    for field in _PROFILE_FIELDS:
        new_val = arguments.get(field, "")
        if isinstance(new_val, str) and new_val.strip():
            old_val = getattr(profile, field, "")
            if new_val.strip() != old_val:
                setattr(profile, field, new_val.strip())
                changed = True

    # Tone proposal handling (§6.7)
    tone_tags_raw = arguments.get("tone_tags")
    tone_source = arguments.get("tone_update_source", "implicit")
    tone_confidence = float(arguments.get("tone_confidence", 1.0))

    if tone_tags_raw:
        if isinstance(tone_tags_raw, str):
            try:
                tone_tags_raw = json.loads(tone_tags_raw)
            except json.JSONDecodeError:
                tone_tags_raw = [tone_tags_raw]
        tags, _ = validate_proposal(tone_tags_raw)
        if tags:
            new_tone = update_profile_tone(
                profile.tone,
                tags,
                source=tone_source,
                confidence=tone_confidence,
            )
            if new_tone != profile.tone:
                profile.tone = new_tone
                changed = True

    if changed:
        _save_user_profile(state_data, profile)
        return "success"
    return "noop"


# ---------------------------------------------------------------------------
# SchedulerTool (§4.4)
# ---------------------------------------------------------------------------

DEFAULT_FIXED_TIMEZONE = "America/Toronto"
DEFAULT_RANDOM_TIMEZONE = "UTC"


def _load_schedule_registry(state_data: StateData) -> list[ScheduleInfo]:
    raw = _get_state(state_data, DataKey.SCHEDULE_REGISTRY, "[]")
    try:
        items = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return [ScheduleInfo.model_validate(i) for i in items]


def _save_schedule_registry(
    state_data: StateData, schedules: list[ScheduleInfo]
) -> None:
    _set_state(
        state_data,
        DataKey.SCHEDULE_REGISTRY,
        json.dumps([s.model_dump(mode="json") for s in schedules]),
    )


def execute_scheduler(
    state_data: StateData,
    arguments: dict[str, Any],
) -> str:
    """Dispatch scheduler actions: create / list / delete (§4.4)."""
    action = arguments.get("action", "")

    if action == "create":
        return _execute_create_schedule(state_data, arguments)
    if action == "list":
        return _execute_list_schedules(state_data)
    if action == "delete":
        return _execute_delete_schedule(state_data, arguments)

    return f"error: unknown scheduler action '{action}'"


def _execute_create_schedule(
    state_data: StateData,
    arguments: dict[str, Any],
) -> str:
    stype = arguments.get("type", "fixed")
    tz = arguments.get("timezone", "")

    if not tz:
        tz = DEFAULT_FIXED_TIMEZONE if stype == "fixed" else DEFAULT_RANDOM_TIMEZONE

    schedule = ScheduleInfo(
        id=str(uuid.uuid4())[:8],
        type=stype,
        fixed_time=arguments.get("fixed_time"),
        random_start_time=arguments.get("random_start_time"),
        random_end_time=arguments.get("random_end_time"),
        timezone=tz,
        created_at=datetime.now(timezone.utc),
        timer_id=f"schedule_{uuid.uuid4().hex[:12]}",
    )

    schedules = _load_schedule_registry(state_data)
    schedules.append(schedule)
    _save_schedule_registry(state_data, schedules)
    return f"success: schedule '{schedule.id}' created"


def _execute_list_schedules(state_data: StateData) -> str:
    schedules = _load_schedule_registry(state_data)
    if not schedules:
        return "No schedules configured."
    lines = [f"- {s.id}: type={s.type}, tz={s.timezone}" for s in schedules]
    return "Schedules:\n" + "\n".join(lines)


def _execute_delete_schedule(
    state_data: StateData,
    arguments: dict[str, Any],
) -> str:
    sid = arguments.get("schedule_id", "")
    if not sid:
        return "error: schedule_id required for delete"

    schedules = _load_schedule_registry(state_data)
    new = [s for s in schedules if s.id != sid]
    if len(new) == len(schedules):
        return f"error: schedule '{sid}' not found"
    _save_schedule_registry(state_data, new)
    return f"success: schedule '{sid}' deleted"


# ---------------------------------------------------------------------------
# PromptGeneratorTool (§4.5)
# ---------------------------------------------------------------------------


def execute_prompt_generator(
    state_data: StateData,
    arguments: dict[str, Any],
) -> str:
    """Validate profile and generate a habit prompt (§4.5).

    PromptAnchor and PreferredTime are mandatory.
    """
    profile = get_or_create_user_profile(state_data)

    if not profile.prompt_anchor:
        return "error: PromptAnchor is required but missing from profile"
    if not profile.preferred_time:
        return "error: PreferredTime is required but missing from profile"

    warnings: list[str] = []
    if not profile.habit_domain:
        warnings.append("HabitDomain not set")
    if not profile.motivational_frame:
        warnings.append("MotivationalFrame not set")

    # delivery_mode = arguments.get("delivery_mode", "immediate")
    notes = arguments.get("personalization_notes", "")

    # Stub LLM call — produce a deterministic prompt
    prompt = (
        f"Time to work on your habit! "
        f"Anchor: {profile.prompt_anchor}. "
        f"Preferred time: {profile.preferred_time}."
    )
    if notes:
        prompt += f" Note: {notes}"

    # Store result
    _set_state(state_data, DataKey.LAST_HABIT_PROMPT, prompt)

    # Increment total prompts
    profile.total_prompts += 1
    _save_user_profile(state_data, profile)

    result = prompt
    if warnings:
        result += f" (warnings: {', '.join(warnings)})"
    return result


# ---------------------------------------------------------------------------
# StateTransitionTool (§4.6)
# ---------------------------------------------------------------------------


def execute_state_transition(
    state_data: StateData,
    arguments: dict[str, Any],
) -> str:
    """Immediate or delayed state transitions (§4.6)."""
    target = arguments.get("target_state", "")
    delay_minutes = float(arguments.get("delay_minutes", 0))
    reason = arguments.get("reason", "")

    if target not in (ConversationState.INTAKE.value, ConversationState.FEEDBACK.value):
        return f"error: invalid target_state '{target}'"

    if delay_minutes > 0:
        # Schedule delayed transition — store intent
        timer_id = f"state_transition_{uuid.uuid4().hex[:12]}"
        _set_state(state_data, DataKey.STATE_TRANSITION_TIMER_ID, timer_id)
        return (
            f"success: transition to {target} scheduled in "
            f"{delay_minutes} minutes (timer={timer_id})"
        )

    # Immediate transition
    _set_state(state_data, DataKey.CONVERSATION_STATE, target)

    # Cancel pending auto-feedback timer on immediate transition (§4.6)
    _set_state(state_data, DataKey.AUTO_FEEDBACK_TIMER_ID, "")

    msg = f"success: transitioned to {target}"
    if reason:
        msg += f" (reason: {reason})"
    return msg


# ---------------------------------------------------------------------------
# Tool dispatcher
# ---------------------------------------------------------------------------

TOOL_REGISTRY: dict[str, Any] = {
    "save_user_profile": execute_profile_save,
    "scheduler": execute_scheduler,
    "generate_habit_prompt": execute_prompt_generator,
    "transition_state": execute_state_transition,
}


def execute_tool(
    state_data: StateData,
    tool_call: ToolCall,
) -> ToolResult:
    """Execute a single tool call and return a result string (§8.1)."""
    handler = TOOL_REGISTRY.get(tool_call.name)
    if handler is None:
        return ToolResult(
            tool_call_id=tool_call.id,
            name=tool_call.name,
            result=f"error: unknown tool '{tool_call.name}'",
        )
    try:
        result_str = handler(state_data, tool_call.arguments)
    except Exception as exc:  # noqa: BLE001
        result_str = f"error: {exc}"
    return ToolResult(
        tool_call_id=tool_call.id,
        name=tool_call.name,
        result=result_str,
    )
