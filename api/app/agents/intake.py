"""Intake specialist agent — LangChain tool-calling agent.

Uses the LangGraph-backed agent so the LLM drives the tool loop
via the framework — no hand-rolled iteration.
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import HumanMessage
from langgraph.graph.state import CompiledStateGraph

from app.prompt_loader import load_prompt

INTAKE_SYSTEM_PROMPT = load_prompt("intake_system")

INTAKE_FALLBACK = (
    "I'd love to help you set up your habit-building routine! "
    "Could you tell me more about the habit you'd like to work on?"
)

_RECURSION_LIMIT = 22


def run_intake(
    agent: CompiledStateGraph,
    user_text: str,
    chat_history: list[Any],
) -> str:
    """Invoke the intake agent and return the assistant text.

    Falls back to ``INTAKE_FALLBACK`` if the agent produces no output.
    """
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
    return INTAKE_FALLBACK
