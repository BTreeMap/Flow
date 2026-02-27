"""Intake specialist agent — LangChain tool-calling agent.

Uses the LangGraph-backed agent so the LLM drives the tool loop
via the framework — no hand-rolled iteration.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any

from langgraph.graph.state import CompiledStateGraph

from app.agents.runner import run_agent
from app.prompt_loader import load_prompt

INTAKE_SYSTEM_PROMPT = load_prompt("intake_system")

INTAKE_FALLBACK = (
    "I'd love to help you set up your habit-building routine! "
    "Could you tell me more about the habit you'd like to work on?"
)


async def run_intake(
    agent: CompiledStateGraph,
    user_text: str,
    chat_history: list[Any],
    on_token: Callable[[str], Coroutine[None, None, None]] | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """Invoke the intake agent and return (assistant_text, tool_calls).

    Falls back to ``INTAKE_FALLBACK`` if the agent produces no output.
    """
    return await run_agent(
        agent=agent,
        user_text=user_text,
        chat_history=chat_history,
        fallback_text=INTAKE_FALLBACK,
        on_token=on_token,
    )
