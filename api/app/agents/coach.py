"""Coach specialist agent — normal conversation and nudges.

The Coach handles general conversation. It can propose candidate patches
but has no direct write permissions. All proposals go through Router validation
with higher confidence thresholds.
"""

from __future__ import annotations

from typing import Any

from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langgraph.graph.state import CompiledStateGraph

from app.tools.proposal_tools import ProposalCollector, make_proposal_tools

COACH_SYSTEM_PROMPT = (
    "You are a supportive habit coach. Help the user stay on track with their habits. "
    "Provide encouragement, suggestions, and accountability. "
    "If the user shares relevant preferences or patterns, propose them via "
    "propose_profile_patch or propose_memory_patch tools. "
    "You must NOT claim to directly update the profile or memory — you can only propose candidates. "
    "The Router will decide whether to commit your proposals."
)

COACH_FALLBACK = (
    "I'm here to support your habit journey. "
    "How can I help you today?"
)

_RECURSION_LIMIT = 22


def create_coach_agent(
    llm: BaseChatModel,
    collector: ProposalCollector,
    system_prompt: str = COACH_SYSTEM_PROMPT,
) -> CompiledStateGraph:
    """Build a LangGraph agent for the Coach specialist."""
    tools = make_proposal_tools(collector, source_bot="COACH")
    return create_agent(llm, tools=tools, system_prompt=system_prompt)


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
