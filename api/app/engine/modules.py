"""IntakeModule and FeedbackModule — tool loop implementation (§4.2, §4.3, §8)."""

from __future__ import annotations

import json
from typing import Any, Protocol

from app.engine.state import (
    ConversationMessage,
    DataKey,
    UserProfile,
)
from app.engine.tone import build_tone_guide
from app.engine.tools import (
    StateData,
    ToolCall,
    _get_state,
    execute_tool,
    get_or_create_user_profile,
)

MAX_TOOL_ROUNDS = 10

INTAKE_FALLBACK = (
    "I'm here to help you set up your habit-building routine. "
    "Could you tell me more about the habit you'd like to work on?"
)
FEEDBACK_FALLBACK = (
    "I'd love to hear how things went with your habit today. "
    "Feel free to share any updates!"
)


# ---------------------------------------------------------------------------
# LLM response stub / injection protocol
# ---------------------------------------------------------------------------


class LLMResponse:
    """Represents one LLM response (content and/or tool calls)."""

    def __init__(
        self,
        content: str = "",
        tool_calls: list[ToolCall] | None = None,
    ) -> None:
        self.content = content
        self.tool_calls = tool_calls or []


class LLMClient(Protocol):
    """Protocol for an injectable LLM client."""

    def generate(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse: ...


class StubLLMClient:
    """Default stub LLM client for prototype / testing.

    Returns a simple response on the first call.  Can be pre-loaded with
    a sequence of responses for testing the tool loop.
    """

    def __init__(self, responses: list[LLMResponse] | None = None) -> None:
        self._responses = list(responses) if responses else []
        self._call_idx = 0

    def generate(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        if self._call_idx < len(self._responses):
            resp = self._responses[self._call_idx]
            self._call_idx += 1
            return resp
        # Default: return a simple text response
        return LLMResponse(content="I'm here to help with your habit journey.")


# ---------------------------------------------------------------------------
# Tool definitions exposed to LLM (OpenAI function-calling format)
# ---------------------------------------------------------------------------

INTAKE_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "save_user_profile",
            "description": "Save or update user profile fields.",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt_anchor": {"type": "string"},
                    "preferred_time": {"type": "string"},
                    "habit_domain": {"type": "string"},
                    "motivational_frame": {"type": "string"},
                    "additional_info": {"type": "string"},
                    "last_successful_prompt": {"type": "string"},
                    "last_barrier": {"type": "string"},
                    "last_motivator": {"type": "string"},
                    "last_tweak": {"type": "string"},
                    "tone_tags": {"type": "array", "items": {"type": "string"}},
                    "tone_update_source": {"type": "string"},
                    "tone_confidence": {"type": "number"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "scheduler",
            "description": "Create, list, or delete schedules.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["create", "list", "delete"]},
                    "type": {"type": "string", "enum": ["fixed", "random"]},
                    "fixed_time": {"type": "string"},
                    "timezone": {"type": "string"},
                    "random_start_time": {"type": "string"},
                    "random_end_time": {"type": "string"},
                    "schedule_id": {"type": "string"},
                },
                "required": ["action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_habit_prompt",
            "description": "Generate a habit prompt for the user.",
            "parameters": {
                "type": "object",
                "properties": {
                    "delivery_mode": {
                        "type": "string",
                        "enum": ["immediate", "scheduled"],
                    },
                    "personalization_notes": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "transition_state",
            "description": "Transition conversation state.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target_state": {
                        "type": "string",
                        "enum": ["INTAKE", "FEEDBACK"],
                    },
                    "delay_minutes": {"type": "number"},
                    "reason": {"type": "string"},
                },
                "required": ["target_state"],
            },
        },
    },
]

FEEDBACK_TOOLS: list[dict[str, Any]] = [
    INTAKE_TOOLS[0],  # save_user_profile
    INTAKE_TOOLS[1],  # scheduler
    INTAKE_TOOLS[3],  # transition_state
]


# ---------------------------------------------------------------------------
# Message context construction (§8.2)
# ---------------------------------------------------------------------------


def _build_profile_context(profile: UserProfile) -> str:
    """Build a context block summarizing current profile state."""
    lines = ["<PROFILE STATUS>"]
    fields = [
        ("PromptAnchor", profile.prompt_anchor),
        ("PreferredTime", profile.preferred_time),
        ("HabitDomain", profile.habit_domain),
        ("MotivationalFrame", profile.motivational_frame),
        ("Intensity", profile.intensity),
        ("TotalPrompts", str(profile.total_prompts)),
        ("SuccessCount", str(profile.success_count)),
    ]
    for name, val in fields:
        status = val if val else "(not set)"
        lines.append(f"  {name}: {status}")
    lines.append("</PROFILE STATUS>")
    return "\n".join(lines)


def _build_messages(
    system_prompt: str,
    state_data: StateData,
    user_message: str,
    chat_history: list[ConversationMessage],
    tool_context: list[dict[str, Any]],
    max_history_messages: int = 30,
) -> list[dict[str, Any]]:
    """Construct the full message array per §8.2.

    [system prompt] + [context block] + [tone guide] + [chat history]
    + [user message] + [tool call/result pairs from this loop]
    """
    messages: list[dict[str, Any]] = []

    # System prompt
    messages.append({"role": "system", "content": system_prompt})

    # Context block
    profile = get_or_create_user_profile(state_data)
    bg = _get_state(state_data, DataKey.PARTICIPANT_BACKGROUND)
    context_parts: list[str] = []
    if bg:
        context_parts.append(f"<PARTICIPANT BACKGROUND>\n{bg}\n</PARTICIPANT BACKGROUND>")
    context_parts.append(_build_profile_context(profile))
    messages.append({"role": "system", "content": "\n\n".join(context_parts)})

    # Tone guide
    tone_guide = build_tone_guide(profile.tone)
    if tone_guide:
        messages.append({"role": "system", "content": tone_guide})

    # Chat history (most recent max_history_messages)
    trimmed = chat_history[-max_history_messages:]
    for msg in trimmed:
        messages.append({"role": msg.role, "content": msg.content})

    # Current user message
    if user_message:
        messages.append({"role": "user", "content": user_message})

    # Tool call/result pairs accumulated in this loop
    messages.extend(tool_context)

    return messages


# ---------------------------------------------------------------------------
# IntakeModule (§4.2)
# ---------------------------------------------------------------------------


class IntakeModule:
    """Intake conversation module with tool loop (§4.2, §8)."""

    def __init__(
        self,
        system_prompt: str = "",
        llm_client: LLMClient | None = None,
    ) -> None:
        self.system_prompt = system_prompt or "You are a habit-building intake assistant."
        self._llm = llm_client or StubLLMClient()

    def execute(
        self,
        state_data: StateData,
        user_message: str,
        chat_history: list[ConversationMessage],
    ) -> str:
        """Run the intake tool loop. Returns assistant text (§8.1)."""
        tool_context: list[dict[str, Any]] = []

        for _round in range(MAX_TOOL_ROUNDS):
            messages = _build_messages(
                self.system_prompt,
                state_data,
                user_message,
                chat_history,
                tool_context,
            )
            response = self._llm.generate(messages, tools=INTAKE_TOOLS)

            # §8.1 — Terminate on content
            if response.content:
                return response.content

            # §8.1 — Execute tool calls if no content
            if response.tool_calls:
                for tc in response.tool_calls:
                    result = execute_tool(state_data, tc)
                    # Append assistant tool-call + tool result to context
                    tool_context.append({
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {
                                    "name": tc.name,
                                    "arguments": json.dumps(tc.arguments),
                                },
                            }
                        ],
                    })
                    tool_context.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result.result,
                    })
                continue

            # §8.1 — No content and no tool calls → fallback
            return INTAKE_FALLBACK

        # §8.1 — Max rounds exhausted
        return INTAKE_FALLBACK


# ---------------------------------------------------------------------------
# FeedbackModule (§4.3)
# ---------------------------------------------------------------------------


class FeedbackModule:
    """Feedback tracking module with tool loop (§4.3, §8)."""

    def __init__(
        self,
        system_prompt: str = "",
        llm_client: LLMClient | None = None,
    ) -> None:
        self.system_prompt = system_prompt or "You are a habit feedback tracker."
        self._llm = llm_client or StubLLMClient()

    def execute(
        self,
        state_data: StateData,
        user_message: str,
        chat_history: list[ConversationMessage],
    ) -> str:
        """Run the feedback tool loop. Returns assistant text (§8.1)."""
        tool_context: list[dict[str, Any]] = []

        for _round in range(MAX_TOOL_ROUNDS):
            messages = _build_messages(
                self.system_prompt,
                state_data,
                user_message,
                chat_history,
                tool_context,
            )
            response = self._llm.generate(messages, tools=FEEDBACK_TOOLS)

            if response.content:
                return response.content

            if response.tool_calls:
                for tc in response.tool_calls:
                    result = execute_tool(state_data, tc)
                    tool_context.append({
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {
                                    "name": tc.name,
                                    "arguments": json.dumps(tc.arguments),
                                },
                            }
                        ],
                    })
                    tool_context.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result.result,
                    })
                continue

            return FEEDBACK_FALLBACK

        return FEEDBACK_FALLBACK

    def cancel_pending_feedback(self, state_data: StateData) -> None:
        """Cancel feedbackTimerID and feedbackFollowupTimerID (§4.3)."""
        state_data[DataKey.FEEDBACK_TIMER_ID.value] = ""
        state_data[DataKey.FEEDBACK_FOLLOWUP_TIMER_ID.value] = ""
