"""Specialist invocation helpers — stubs, summaries, and the agent factory."""

from __future__ import annotations

import string

from langchain_core.language_models import BaseChatModel
from langgraph.graph.state import CompiledStateGraph

from app.prompt_loader import load_prompt
from app.schemas.patches import MemoryItemData, UserProfileData
from app.tools.proposal_tools import ProposalCollector

# ---------------------------------------------------------------------------
# Specialist invocation (stub mode for when no LLM is available)
# ---------------------------------------------------------------------------


def _run_specialist_stub(route: str, user_text: str) -> tuple[str, ProposalCollector]:
    """Stub specialist invocation for testing without LLM."""
    collector = ProposalCollector()
    if route == "INTAKE":
        text = (
            "I'm here to help you set up your habit-building routine. "
            "Could you tell me more about the habit you'd like to work on?"
        )
    elif route == "FEEDBACK":
        text = (
            "I'd love to hear how things went with your habit today. "
            "Feel free to share any updates!"
        )
    else:
        text = "I'm here to support your habit journey. How can I help you today?"
    return text, collector


def _build_profile_summary(profile: UserProfileData) -> str:
    """Build a summary string for the router."""
    return (
        f"PromptAnchor={'set' if profile.prompt_anchor else 'missing'}, "
        f"PreferredTime={'set' if profile.preferred_time else 'missing'}, "
        f"HabitDomain={'set' if profile.habit_domain else 'missing'}, "
        f"Intensity={profile.intensity}"
    )


def _build_memory_summary(items: list[MemoryItemData]) -> str:
    """Build a summary string from memory items."""
    if not items:
        return "No memory items yet."
    summaries = [item.content[:100] for item in items[-5:]]
    return "; ".join(summaries)


def _strip_feedback_plan_line(text: str) -> str:
    """Remove the internal PLAN line from the Feedback bot's reply.

    The upgraded feedback prompt requires the model to emit a single PLAN
    line followed by a ``---`` separator and the user-visible reply. The
    PLAN line is internal-only and must never be shown to the user.
    """
    if not text:
        return text
    # Match an optional leading PLAN line and the following separator.
    if "---" in text:
        head, _, rest = text.partition("---")
        head_stripped = head.strip()
        if not head_stripped or head_stripped.upper().startswith("PLAN:"):
            return rest.lstrip("\n").strip()
    # Fallback: drop a single leading line that starts with "PLAN:".
    lines = text.splitlines()
    if lines and lines[0].strip().upper().startswith("PLAN:"):
        return "\n".join(lines[1:]).strip()
    return text


# ---------------------------------------------------------------------------
# Specialist agent factory
# ---------------------------------------------------------------------------

_RECURSION_LIMIT = 22


class _SafeDict(dict):
    """Dict subclass that returns '{key}' for missing keys instead of raising."""

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def _create_specialist_agent(
    llm: BaseChatModel,
    tools: list,
    prompt_name: str,
    prompt_args: dict[str, str] | None = None,
) -> CompiledStateGraph:
    """Build a LangGraph agent for a specialist using a prompt loaded from file."""
    from langgraph.prebuilt import create_react_agent

    text = load_prompt(prompt_name)
    if prompt_args:
        # Use string.Template to safely interpolate $variables while ignoring {} braces
        text = string.Template(text).safe_substitute(prompt_args)

    return create_react_agent(llm, tools=tools, prompt=text)
