"""Coach specialist agent — normal conversation and nudges.

The Coach handles general conversation. It can propose candidate patches
but has no direct write permissions. All proposals go through Router validation
with higher confidence thresholds.
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import HumanMessage
from langgraph.graph.state import CompiledStateGraph

from app.prompt_loader import load_prompt

COACH_SYSTEM_PROMPT = load_prompt("coach_system")

COACH_FALLBACK = "I'm here to support your habit journey. How can I help you today?"

_RECURSION_LIMIT = 22


def run_coach(
    agent: CompiledStateGraph,
    user_text: str,
    chat_history: list[Any],
) -> str:
    """Invoke the coach agent and return the assistant text."""
    messages = list(chat_history) + [HumanMessage(content=user_text)]
    result = agent.invoke(
        {"messages": messages},
        config={"recursion_limit": _RECURSION_LIMIT},
    )
    output_messages = result.get("messages", [])
    if output_messages:
        last = output_messages[-1]
        if hasattr(last, "content") and last.content:
            return str(last.content)
    return COACH_FALLBACK
