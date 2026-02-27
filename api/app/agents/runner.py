"""Shared agent runner logic to avoid duplication."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any

from langchain_core.messages import HumanMessage
from langgraph.graph.state import CompiledStateGraph

_RECURSION_LIMIT = 22


async def run_agent(
    agent: CompiledStateGraph,
    user_text: str,
    chat_history: list[Any],
    fallback_text: str,
    on_token: Callable[[str], Coroutine[None, None, None]] | None = None,
) -> str:
    """Run an agent with optional token streaming.

    Args:
        agent: The compiled LangGraph agent to run.
        user_text: The user's input text.
        chat_history: Recent chat history.
        fallback_text: Text to return if the agent produces no output.
        on_token: Optional async callback for streaming tokens.

    Returns:
        The final assistant response text.
    """
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
                # Stream chat model text delta
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

    return final_content or fallback_text
