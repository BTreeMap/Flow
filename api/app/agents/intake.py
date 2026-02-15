"""Intake specialist agent — LangChain tool-calling agent (§4.2).

Uses ``create_agent`` (LangGraph-backed) so the LLM drives the tool loop
via the framework — no hand-rolled iteration.
"""

from __future__ import annotations

from typing import Any

from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langgraph.graph.state import CompiledStateGraph

from app.engine.modules import INTAKE_FALLBACK, MAX_TOOL_ROUNDS
from app.engine.tools import StateData
from app.tools.langchain_tools import make_intake_tools

# Default system prompt for the Intake agent
INTAKE_SYSTEM_PROMPT = (
    "You are a habit-building intake assistant. "
    "Help the user set up their profile, preferred time, habit domain, "
    "and schedule. Use the provided tools to save profile data, "
    "manage schedules, generate habit prompts, and transition state. "
    "Follow the legacy contract rules for intake conversations."
)

# Each LangGraph step is one node execution.  A tool-calling round involves
# two nodes (agent → tool), so ``MAX_TOOL_ROUNDS * 2 + 2`` is a safe
# recursion limit that mirrors the legacy 10-round cap.
_RECURSION_LIMIT = MAX_TOOL_ROUNDS * 2 + 2


def create_intake_agent(
    llm: BaseChatModel,
    state_data: StateData,
    system_prompt: str = INTAKE_SYSTEM_PROMPT,
) -> CompiledStateGraph:
    """Build a LangGraph agent for the Intake specialist."""
    tools = make_intake_tools(state_data)
    return create_agent(llm, tools=tools, system_prompt=system_prompt)


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
