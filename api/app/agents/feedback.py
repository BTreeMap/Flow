"""Feedback specialist agent — LangChain tool-calling agent.

Mirrors the Intake agent pattern but with feedback-specific tools and
system prompt.
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import HumanMessage
from langgraph.graph.state import CompiledStateGraph

from app.prompt_loader import load_prompt

FEEDBACK_SYSTEM_PROMPT = load_prompt("feedback_system")

FEEDBACK_FALLBACK = (
    "I'd love to hear how things went with your habit today. "
    "Feel free to share any updates!"
)

_RECURSION_LIMIT = 22


def run_feedback(
    agent: CompiledStateGraph,
    user_text: str,
    chat_history: list[Any],
) -> str:
    """Invoke the feedback agent and return the assistant text.

    Falls back to ``FEEDBACK_FALLBACK`` if the agent produces no output.
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
    return FEEDBACK_FALLBACK
