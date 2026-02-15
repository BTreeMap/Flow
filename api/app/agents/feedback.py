"""Feedback specialist agent — LangChain tool-calling agent (§4.3).

Mirrors the Intake agent pattern but with feedback-specific tools and
system prompt.
"""

from __future__ import annotations

from typing import Any

from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langgraph.graph.state import CompiledStateGraph

from app.engine.modules import FEEDBACK_FALLBACK, MAX_TOOL_ROUNDS
from app.engine.tools import StateData
from app.tools.langchain_tools import make_feedback_tools

# Default system prompt for the Feedback agent
FEEDBACK_SYSTEM_PROMPT = (
    "You are a habit feedback tracker. "
    "Help the user reflect on their habit progress, identify barriers, "
    "and celebrate successes. Use the provided tools to save feedback data, "
    "manage schedules, and transition state. "
    "Follow the legacy contract rules for feedback conversations."
)

# Recursion limit matching legacy MAX_TOOL_ROUNDS
_RECURSION_LIMIT = MAX_TOOL_ROUNDS * 2 + 2


def create_feedback_agent(
    llm: BaseChatModel,
    state_data: StateData,
    system_prompt: str = FEEDBACK_SYSTEM_PROMPT,
) -> CompiledStateGraph:
    """Build a LangGraph agent for the Feedback specialist."""
    tools = make_feedback_tools(state_data)
    return create_agent(llm, tools=tools, system_prompt=system_prompt)


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
