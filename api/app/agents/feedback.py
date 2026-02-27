"""Feedback specialist agent — LangChain tool-calling agent.

Mirrors the Intake agent pattern but with feedback-specific tools and
system prompt.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
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


async def run_feedback(
    agent: CompiledStateGraph,
    user_text: str,
    chat_history: list[Any],
    on_token: Callable[[str], Coroutine[None, None, None]] | None = None,
) -> str:
    """Invoke the feedback agent and return the assistant text.

    Falls back to ``FEEDBACK_FALLBACK`` if the agent produces no output.
    """
    messages = list(chat_history) + [HumanMessage(content=user_text)]

    final_content = ""

    if on_token:
        async for event in agent.astream_events(
            {"messages": messages},
            version="v2",
            config={"recursion_limit": _RECURSION_LIMIT},
        ):
            if event["event"] == "on_chat_model_stream":
                chunk = event["data"].get("chunk")
                if chunk and hasattr(chunk, "content") and chunk.content:
                    await on_token(chunk.content)
                    final_content += chunk.content
    else:
        result = await agent.ainvoke(
            {"messages": messages},
            config={"recursion_limit": _RECURSION_LIMIT},
        )
        output_messages = result.get("messages", [])
        if output_messages:
            last = output_messages[-1]
            if hasattr(last, "content") and last.content:
                final_content = str(last.content)

    return final_content or FEEDBACK_FALLBACK
