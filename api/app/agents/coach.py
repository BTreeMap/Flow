"""Coach specialist agent — normal conversation and nudges.

The Coach handles general conversation. It can propose candidate patches
but has no direct write permissions. All proposals go through Router validation
with higher confidence thresholds.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any

from langchain_core.messages import HumanMessage
from langgraph.graph.state import CompiledStateGraph

from app.prompt_loader import load_prompt

COACH_SYSTEM_PROMPT = load_prompt("coach_system")

COACH_FALLBACK = "I'm here to support your habit journey. How can I help you today?"

_RECURSION_LIMIT = 22


async def run_coach(
    agent: CompiledStateGraph,
    user_text: str,
    chat_history: list[Any],
    on_token: Callable[[str], Coroutine[None, None, None]] | None = None,
) -> str:
    """Invoke the coach agent and return the assistant text."""
    messages = list(chat_history) + [HumanMessage(content=user_text)]

    final_content = ""

    if on_token:
        # Stream events to capture tokens
        async for event in agent.astream_events(
            {"messages": messages},
            version="v2",
            config={"recursion_limit": _RECURSION_LIMIT},
        ):
            if event["event"] == "on_chat_model_stream":
                # Only stream the final LLM response, not tool calls
                # In ReAct, the final response usually comes when tool usage is done
                # or if the model answers directly.
                # Ideally, we filter by node or ensure it's the 'agent' node emitting text.
                # For simplicity, we stream all chat model text delta.
                chunk = event["data"].get("chunk")
                if chunk and hasattr(chunk, "content") and chunk.content:
                    await on_token(chunk.content)
                    final_content += chunk.content
    else:
        # Fallback to invoke if no streaming callback
        result = await agent.ainvoke(
            {"messages": messages},
            config={"recursion_limit": _RECURSION_LIMIT},
        )
        output_messages = result.get("messages", [])
        if output_messages:
            last = output_messages[-1]
            if hasattr(last, "content") and last.content:
                final_content = str(last.content)

    return final_content or COACH_FALLBACK
