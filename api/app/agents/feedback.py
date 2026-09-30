"""Feedback specialist agent — LangChain tool-calling agent.

Mirrors the Intake agent pattern but with feedback-specific tools and
system prompt.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any

from langchain_core.messages import SystemMessage
from langgraph.graph.state import CompiledStateGraph

from app.agents.runner import run_agent

FEEDBACK_SYSTEM_PROMPT = (
    "You are a sterile telemetry extractor. Analyze the recent conversation and "
    "output ONLY factual state updates regarding the user's behavior. You are "
    "strictly FORBIDDEN from recording, summarizing, or emulating the coaching "
    "style, implementation intentions, structural phrasing, or advice provided by "
    "the system assistant."
)

FEEDBACK_FALLBACK = "I'd love to hear how things went with your habit today. Feel free to share any updates!"


async def run_feedback(
    agent: CompiledStateGraph,
    user_text: str,
    chat_history: list[Any],
    on_token: Callable[[str], Coroutine[None, None, None]] | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """Invoke the feedback agent and return (assistant_text, tool_calls).

    Falls back to ``FEEDBACK_FALLBACK`` if the agent produces no output.
    """
    filtered_history = [
        message for message in chat_history if not isinstance(message, SystemMessage)
    ]
    constrained_history = [
        SystemMessage(content=FEEDBACK_SYSTEM_PROMPT),
        *filtered_history,
    ]
    return await run_agent(
        agent=agent,
        user_text=user_text,
        chat_history=constrained_history,
        fallback_text=FEEDBACK_FALLBACK,
        on_token=on_token,
    )
