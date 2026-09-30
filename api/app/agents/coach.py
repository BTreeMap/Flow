"""Coach specialist agent — normal conversation and nudges.

The Coach handles general conversation. It can propose candidate patches
but has no direct write permissions. All proposals go through Router validation
with higher confidence thresholds.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph.state import CompiledStateGraph

from app.agents.runner import run_agent
from app.prompt_loader import load_prompt
from app.services.condition_filters import contains_condition_c_framing

COACH_SYSTEM_PROMPT = load_prompt("coach_system")

COACH_FALLBACK = "I'm here to support your habit journey. How can I help you today?"
MAX_CONDITION_C_REWRITE_ATTEMPTS = 3
CONDITION_C_REWRITE_INSTRUCTION = (
    "Your previous reply contained forbidden conditional planning, commitment, "
    "or reward framing. Rewrite the reply so it is encouraging but contains "
    "NO if/then or when/then structure, NO commitment contract, NO promise, "
    "and NONE of these words: if-then, when-then, commit, commitment, contract, "
    "promise, reward yourself, bet. Keep the same intent, the same length, "
    "and the same supportive tone."
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
        if not contains_condition_c_framing(assistant_text):
            return assistant_text, tool_calls
        if attempt < MAX_CONDITION_C_REWRITE_ATTEMPTS - 1:
            gated_history.append(AIMessage(content=assistant_text))
            gated_history.append(HumanMessage(content=CONDITION_C_REWRITE_INSTRUCTION))

    return assistant_text, tool_calls
