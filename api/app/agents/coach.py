"""Coach specialist agent — normal conversation and nudges.

The Coach handles general conversation. It can propose candidate patches
but has no direct write permissions. All proposals go through Router validation
with higher confidence thresholds.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any

from langgraph.graph.state import CompiledStateGraph

from app.agents.runner import run_agent
from app.prompt_loader import load_prompt

COACH_SYSTEM_PROMPT = load_prompt("coach_system")

COACH_FALLBACK = "I'm here to support your habit journey. How can I help you today?"


async def run_coach(
    agent: CompiledStateGraph,
    user_text: str,
    chat_history: list[Any],
    on_token: Callable[[str], Coroutine[None, None, None]] | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """Invoke the coach agent and return (assistant_text, tool_calls)."""
    return await run_agent(
        agent=agent,
        user_text=user_text,
        chat_history=chat_history,
        fallback_text=COACH_FALLBACK,
        on_token=on_token,
    )
