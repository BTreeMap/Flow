"""Feedback specialist agent — LangChain tool-calling agent.

Mirrors the Intake agent pattern but with feedback-specific tools and
system prompt.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any

from langgraph.graph.state import CompiledStateGraph

from app.agents.runner import run_agent
from app.prompt_loader import load_prompt

FEEDBACK_SYSTEM_PROMPT = load_prompt("feedback_system")

FEEDBACK_FALLBACK = (
    "I'd love to hear how things went with your habit today. "
    "Feel free to share any updates!"
)


async def run_feedback(
    agent: CompiledStateGraph,
    user_text: str,
    chat_history: list[Any],
    on_token: Callable[[str], Coroutine[None, None, None]] | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """Invoke the feedback agent and return (assistant_text, tool_calls).

    Falls back to ``FEEDBACK_FALLBACK`` if the agent produces no output.
    """
    return await run_agent(
        agent=agent,
        user_text=user_text,
        chat_history=chat_history,
        fallback_text=FEEDBACK_FALLBACK,
        on_token=on_token,
    )
