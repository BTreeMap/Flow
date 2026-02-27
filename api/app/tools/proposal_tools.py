"""LangChain tools for patch proposals — used by specialist bots to propose changes."""

from __future__ import annotations

from typing import Any

from langchain_core.tools import tool
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Tool argument schemas
# ---------------------------------------------------------------------------


class ProposeProfilePatchArgs(BaseModel):
    """Arguments for the propose_profile_patch tool."""

    patch: dict = Field(..., description="Partial profile patch (key-value pairs)")
    confidence: float = Field(..., ge=0, le=1, description="Confidence 0-1")
    message_ids: list[int] = Field(..., description="Message IDs supporting this claim")
    quotes: list[str] = Field(
        default_factory=list, description="Short verbatim snippets"
    )
    source_bot: str = Field(..., description="INTAKE, FEEDBACK, or COACH")


class ProposeMemoryPatchArgs(BaseModel):
    """Arguments for the propose_memory_patch tool."""

    items: list[dict] = Field(
        ..., description="List of memory items with 'content' key"
    )
    confidence: float = Field(..., ge=0, le=1, description="Confidence 0-1")
    message_ids: list[int] = Field(..., description="Message IDs supporting this claim")
    quotes: list[str] = Field(
        default_factory=list, description="Short verbatim snippets"
    )
    source_bot: str = Field(..., description="INTAKE, FEEDBACK, or COACH")


class ProposeScheduleNudgeArgs(BaseModel):
    """Arguments for the propose_schedule_nudge tool."""

    topic: str = Field(..., description="The topic or prompt for the daily nudge")
    time: str = Field(..., description="The time of day in HH:MM format (24h)")
    confidence: float = Field(..., ge=0, le=1, description="Confidence 0-1")
    message_ids: list[int] = Field(..., description="Message IDs supporting this claim")
    source_bot: str = Field(..., description="INTAKE, FEEDBACK, or COACH")


class ProposeDeleteScheduleArgs(BaseModel):
    """Arguments for the propose_delete_schedule tool."""

    schedule_id: int = Field(..., description="The ID of the schedule to delete")
    confidence: float = Field(..., ge=0, le=1, description="Confidence 0-1")
    message_ids: list[int] = Field(..., description="Message IDs supporting this claim")
    source_bot: str = Field(..., description="INTAKE, FEEDBACK, or COACH")


# ---------------------------------------------------------------------------
# Proposal collector — accumulates proposals during an agent run
# ---------------------------------------------------------------------------


class ProposalCollector:
    """Collects patch proposals emitted by specialist bots during a turn."""

    def __init__(self) -> None:
        self.profile_proposals: list[dict[str, Any]] = []
        self.memory_proposals: list[dict[str, Any]] = []
        self.schedule_proposals: list[dict[str, Any]] = []

    def add_profile_proposal(self, proposal: dict[str, Any]) -> None:
        self.profile_proposals.append(proposal)

    def add_memory_proposal(self, proposal: dict[str, Any]) -> None:
        self.memory_proposals.append(proposal)

    def add_schedule_proposal(self, proposal: dict[str, Any]) -> None:
        self.schedule_proposals.append(proposal)


# ---------------------------------------------------------------------------
# Factory for proposal tools bound to a collector
# ---------------------------------------------------------------------------


def make_proposal_tools(collector: ProposalCollector, source_bot: str) -> list[Any]:
    """Create propose_profile_patch and propose_memory_patch tools bound to a collector."""

    @tool("propose_profile_patch", args_schema=ProposeProfilePatchArgs)
    def propose_profile_patch(
        patch: dict,
        confidence: float,
        message_ids: list[int],
        quotes: list[str] | None = None,
        source_bot: str = source_bot,
    ) -> dict[str, Any]:
        """Propose a partial update to the user profile. Router will validate and commit or ignore."""
        proposal = {
            "patch": patch,
            "confidence": confidence,
            "evidence": {"message_ids": message_ids, "quotes": quotes or []},
            "source_bot": source_bot,
        }
        collector.add_profile_proposal(proposal)
        return {"status": "proposal_recorded", "source_bot": source_bot}

    @tool("propose_memory_patch", args_schema=ProposeMemoryPatchArgs)
    def propose_memory_patch(
        items: list[dict],
        confidence: float,
        message_ids: list[int],
        quotes: list[str] | None = None,
        source_bot: str = source_bot,
    ) -> dict[str, Any]:
        """Propose adding memory items. Router will validate and commit or ignore."""
        proposal = {
            "items": items,
            "confidence": confidence,
            "evidence": {"message_ids": message_ids, "quotes": quotes or []},
            "source_bot": source_bot,
        }
        collector.add_memory_proposal(proposal)
        return {"status": "proposal_recorded", "source_bot": source_bot}

    @tool("propose_schedule_nudge", args_schema=ProposeScheduleNudgeArgs)
    def propose_schedule_nudge(
        topic: str,
        time: str,
        confidence: float,
        message_ids: list[int],
        source_bot: str = source_bot,
    ) -> dict[str, Any]:
        """Propose scheduling a new daily nudge."""
        proposal = {
            "action": "create",
            "topic": topic,
            "time": time,
            "confidence": confidence,
            "evidence": {"message_ids": message_ids},
            "source_bot": source_bot,
        }
        collector.add_schedule_proposal(proposal)
        return {"status": "proposal_recorded", "source_bot": source_bot}

    @tool("propose_delete_schedule", args_schema=ProposeDeleteScheduleArgs)
    def propose_delete_schedule(
        schedule_id: int,
        confidence: float,
        message_ids: list[int],
        source_bot: str = source_bot,
    ) -> dict[str, Any]:
        """Propose deleting (deactivating) a nudge schedule."""
        proposal = {
            "action": "delete",
            "schedule_id": schedule_id,
            "confidence": confidence,
            "evidence": {"message_ids": message_ids},
            "source_bot": source_bot,
        }
        collector.add_schedule_proposal(proposal)
        return {"status": "proposal_recorded", "source_bot": source_bot}

    return [
        propose_profile_patch,
        propose_memory_patch,
        propose_schedule_nudge,
        propose_delete_schedule,
    ]
