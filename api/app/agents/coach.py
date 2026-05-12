"""Coach specialist agent — normal conversation and nudges.

The Coach handles general conversation. It can propose candidate patches
but has no direct write permissions. All proposals go through Router validation
with higher confidence thresholds.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Coroutine
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph.state import CompiledStateGraph

from app.agents.runner import run_agent
from app.prompt_loader import load_prompt

COACH_SYSTEM_PROMPT = load_prompt("coach_system")

COACH_FALLBACK = "I'm here to support your habit journey. How can I help you today?"
MAX_CONDITION_C_REWRITE_ATTEMPTS = 3
CONDITION_C_PATTERN = re.compile(
    r"(?i)\bif\b.*\bthen\b.*\bwill\b|commitment contract|I bet"
)
CONDITION_C_REWRITE_INSTRUCTION = (
    "Your previous response contained explicit conditional planning. Rewrite the "
    "message to be encouraging but remove any explicit 'if-then' structures or "
    "strict behavioral framing."
)


async def run_coach(
    agent: CompiledStateGraph,
    user_text: str,
    chat_history: list[Any],
    active_condition: str | None = None,
    on_token: Callable[[str], Coroutine[None, None, None]] | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """Invoke the coach agent and return (assistant_text, tool_calls)."""
    if active_condition != "C":
        return await run_agent(
            agent=agent,
            user_text=user_text,
            chat_history=chat_history,
            fallback_text=COACH_FALLBACK,
            on_token=on_token,
        )

    gated_history = list(chat_history)
    assistant_text = COACH_FALLBACK
    tool_calls: list[dict[str, Any]] = []

    for attempt in range(MAX_CONDITION_C_REWRITE_ATTEMPTS):
        assistant_text, tool_calls = await run_agent(
            agent=agent,
            user_text=user_text,
            chat_history=gated_history,
            fallback_text=COACH_FALLBACK,
            on_token=on_token,
        )
        if not CONDITION_C_PATTERN.search(assistant_text):
            return assistant_text, tool_calls
        if attempt < MAX_CONDITION_C_REWRITE_ATTEMPTS - 1:
            gated_history.append(AIMessage(content=assistant_text))
            gated_history.append(HumanMessage(content=CONDITION_C_REWRITE_INSTRUCTION))

    return assistant_text, tool_calls
