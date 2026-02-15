"""LangChain @tool wrappers over the existing engine tool functions.

Each tool accepts Pydantic-typed args and delegates to the existing
engine/tools.py functions, keeping the legacy logic untouched.

Tools are created via factory functions that close over a mutable
``state_data`` dict so the engine layer stays decoupled from persistence.
"""

from __future__ import annotations

from typing import Any

from langchain_core.tools import tool

from app.engine.tools import (
    StateData,
    execute_profile_save,
    execute_prompt_generator,
    execute_scheduler,
    execute_state_transition,
)
from app.schemas.tool_schemas import (
    GenerateHabitPromptArgs,
    GenerateHabitPromptResult,
    ProfileSaveArgs,
    ProfileSaveResult,
    SchedulerArgs,
    SchedulerResult,
    StateTransitionArgs,
    StateTransitionResult,
)


# ---------------------------------------------------------------------------
# Factory helpers — each returns a list of LangChain tools bound to state
# ---------------------------------------------------------------------------


def _make_profile_save_tool(state_data: StateData) -> Any:
    """Create a save_user_profile LangChain tool bound to *state_data*."""

    @tool("save_user_profile", args_schema=ProfileSaveArgs)
    def save_user_profile(
        prompt_anchor: str = "",
        preferred_time: str = "",
        habit_domain: str = "",
        motivational_frame: str = "",
        additional_info: str = "",
        last_successful_prompt: str = "",
        last_barrier: str = "",
        last_motivator: str = "",
        last_tweak: str = "",
        tone_tags: list[str] | None = None,
        tone_update_source: str = "implicit",
        tone_confidence: float = 1.0,
    ) -> dict[str, Any]:
        """Save or update user profile fields. Only non-empty, changed fields are merged."""
        args: dict[str, Any] = {
            "prompt_anchor": prompt_anchor,
            "preferred_time": preferred_time,
            "habit_domain": habit_domain,
            "motivational_frame": motivational_frame,
            "additional_info": additional_info,
            "last_successful_prompt": last_successful_prompt,
            "last_barrier": last_barrier,
            "last_motivator": last_motivator,
            "last_tweak": last_tweak,
            "tone_update_source": tone_update_source,
            "tone_confidence": tone_confidence,
        }
        if tone_tags is not None:
            args["tone_tags"] = tone_tags
        try:
            status = execute_profile_save(state_data, args)
            return ProfileSaveResult(ok=True, status=status).model_dump()
        except Exception as e:
            return ProfileSaveResult(
                ok=False, status="error", error=str(e)
            ).model_dump()

    return save_user_profile


def _make_scheduler_tool(state_data: StateData) -> Any:
    """Create a scheduler LangChain tool bound to *state_data*."""

    @tool("scheduler", args_schema=SchedulerArgs)
    def scheduler(
        action: str,
        type: str | None = None,
        fixed_time: str | None = None,
        timezone: str | None = None,
        random_start_time: str | None = None,
        random_end_time: str | None = None,
        schedule_id: str | None = None,
    ) -> dict[str, Any]:
        """Create, list, or delete schedules."""
        args: dict[str, Any] = {"action": action}
        if type is not None:
            args["type"] = type
        if fixed_time is not None:
            args["fixed_time"] = fixed_time
        if timezone is not None:
            args["timezone"] = timezone
        if random_start_time is not None:
            args["random_start_time"] = random_start_time
        if random_end_time is not None:
            args["random_end_time"] = random_end_time
        if schedule_id is not None:
            args["schedule_id"] = schedule_id
        try:
            result_str = execute_scheduler(state_data, args)
            ok = not result_str.startswith("error")
            return SchedulerResult(
                ok=ok, message=result_str, error=result_str if not ok else None
            ).model_dump()
        except Exception as e:
            return SchedulerResult(ok=False, message="error", error=str(e)).model_dump()

    return scheduler


def _make_prompt_generator_tool(state_data: StateData) -> Any:
    """Create a generate_habit_prompt LangChain tool bound to *state_data*."""

    @tool("generate_habit_prompt", args_schema=GenerateHabitPromptArgs)
    def generate_habit_prompt(
        delivery_mode: str = "immediate",
        personalization_notes: str = "",
    ) -> dict[str, Any]:
        """Generate a habit prompt for the user."""
        args: dict[str, Any] = {
            "delivery_mode": delivery_mode,
            "personalization_notes": personalization_notes,
        }
        try:
            result_str = execute_prompt_generator(state_data, args)
            if result_str.startswith("error:"):
                return GenerateHabitPromptResult(
                    ok=False, error=result_str
                ).model_dump()
            return GenerateHabitPromptResult(ok=True, prompt=result_str).model_dump()
        except Exception as e:
            return GenerateHabitPromptResult(ok=False, error=str(e)).model_dump()

    return generate_habit_prompt


def _make_state_transition_tool(state_data: StateData) -> Any:
    """Create a transition_state LangChain tool bound to *state_data*."""

    @tool("transition_state", args_schema=StateTransitionArgs)
    def transition_state(
        target_state: str,
        delay_minutes: float = 0,
        reason: str = "",
    ) -> dict[str, Any]:
        """Transition conversation sub-state (INTAKE/FEEDBACK)."""
        args: dict[str, Any] = {
            "target_state": target_state,
            "delay_minutes": delay_minutes,
            "reason": reason,
        }
        try:
            result_str = execute_state_transition(state_data, args)
            if result_str.startswith("error:"):
                return StateTransitionResult(ok=False, error=result_str).model_dump()
            if "scheduled" in result_str:
                return StateTransitionResult(
                    ok=True, scheduled_for=result_str
                ).model_dump()
            return StateTransitionResult(
                ok=True, applied_state=target_state
            ).model_dump()
        except Exception as e:
            return StateTransitionResult(ok=False, error=str(e)).model_dump()

    return transition_state


# ---------------------------------------------------------------------------
# Public factories returning tool lists per agent role
# ---------------------------------------------------------------------------


def make_intake_tools(state_data: StateData) -> list[Any]:
    """Return LangChain tools available to the Intake agent (§4.2).

    Intake gets: save_user_profile, scheduler, generate_habit_prompt, transition_state.
    """
    return [
        _make_profile_save_tool(state_data),
        _make_scheduler_tool(state_data),
        _make_prompt_generator_tool(state_data),
        _make_state_transition_tool(state_data),
    ]


def make_feedback_tools(state_data: StateData) -> list[Any]:
    """Return LangChain tools available to the Feedback agent (§4.3).

    Feedback gets: save_user_profile, scheduler, transition_state.
    (No generate_habit_prompt.)
    """
    return [
        _make_profile_save_tool(state_data),
        _make_scheduler_tool(state_data),
        _make_state_transition_tool(state_data),
    ]
