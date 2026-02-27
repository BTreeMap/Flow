"""Tests for LangChain proposal tools (new architecture).

Validates:
- Proposal tools have Pydantic args_schema
- Proposal tools record proposals to the collector
- Proposal tools return structured results
- Proposal tools reject calls missing required payload fields
"""

from __future__ import annotations

from typing import Any

import pytest

from app.tools.proposal_tools import (
    ProposalCollector,
    make_proposal_tools,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_tool(tools: list[Any], name: str) -> Any:
    for t in tools:
        if t.name == name:
            return t
    raise ValueError(f"Tool '{name}' not found in {[t.name for t in tools]}")


# ---------------------------------------------------------------------------
# Tool creation and schema validation
# ---------------------------------------------------------------------------


class TestToolCreation:
    def test_proposal_tools_have_four_tools(self) -> None:
        collector = ProposalCollector()
        tools = make_proposal_tools(collector, source_bot="INTAKE")
        names = sorted(t.name for t in tools)
        assert names == [
            "propose_delete_schedule",
            "propose_memory_patch",
            "propose_profile_patch",
            "propose_schedule_nudge",
        ]

    def test_all_tools_have_args_schema(self) -> None:
        """Every tool must declare a Pydantic args_schema."""
        collector = ProposalCollector()
        for t in make_proposal_tools(collector, source_bot="INTAKE"):
            assert t.args_schema is not None
            assert hasattr(t.args_schema, "model_fields")


# ---------------------------------------------------------------------------
# propose_profile_patch tool
# ---------------------------------------------------------------------------


class TestProfilePatchTool:
    def test_records_proposal_to_collector(self) -> None:
        collector = ProposalCollector()
        tools = make_proposal_tools(collector, source_bot="INTAKE")
        tool = _find_tool(tools, "propose_profile_patch")
        result = tool.invoke(
            {
                "patch": {"prompt_anchor": "after coffee"},
                "confidence": 0.9,
                "message_ids": [1],
                "source_bot": "INTAKE",
            }
        )
        assert result["status"] == "proposal_recorded"
        assert len(collector.profile_proposals) == 1
        assert (
            collector.profile_proposals[0]["patch"]["prompt_anchor"] == "after coffee"
        )

    def test_empty_message_ids_allowed(self) -> None:
        collector = ProposalCollector()
        tools = make_proposal_tools(collector, source_bot="FEEDBACK")
        tool = _find_tool(tools, "propose_profile_patch")
        result = tool.invoke(
            {
                "patch": {"last_barrier": "evening fatigue"},
                "confidence": 0.8,
                "message_ids": [],
                "source_bot": "FEEDBACK",
            }
        )
        assert result["status"] == "proposal_recorded"
        assert len(collector.profile_proposals) == 1

    def test_multiple_proposals_accumulated(self) -> None:
        collector = ProposalCollector()
        tools = make_proposal_tools(collector, source_bot="INTAKE")
        tool = _find_tool(tools, "propose_profile_patch")
        tool.invoke(
            {
                "patch": {"prompt_anchor": "a"},
                "confidence": 0.9,
                "message_ids": [1],
                "source_bot": "INTAKE",
            }
        )
        tool.invoke(
            {
                "patch": {"preferred_time": "8am"},
                "confidence": 0.9,
                "message_ids": [2],
                "source_bot": "INTAKE",
            }
        )
        assert len(collector.profile_proposals) == 2


# ---------------------------------------------------------------------------
# propose_memory_patch tool
# ---------------------------------------------------------------------------


class TestMemoryPatchTool:
    def test_records_memory_proposal(self) -> None:
        collector = ProposalCollector()
        tools = make_proposal_tools(collector, source_bot="FEEDBACK")
        tool = _find_tool(tools, "propose_memory_patch")
        result = tool.invoke(
            {
                "items": [{"content": "User prefers mornings"}],
                "confidence": 0.85,
                "message_ids": [5],
                "source_bot": "FEEDBACK",
            }
        )
        assert result["status"] == "proposal_recorded"
        assert len(collector.memory_proposals) == 1
        assert (
            collector.memory_proposals[0]["items"][0]["content"]
            == "User prefers mornings"
        )

    def test_with_quotes(self) -> None:
        collector = ProposalCollector()
        tools = make_proposal_tools(collector, source_bot="COACH")
        tool = _find_tool(tools, "propose_memory_patch")
        result = tool.invoke(
            {
                "items": [{"content": "Knee pain limits options"}],
                "confidence": 0.7,
                "message_ids": [10],
                "quotes": ["my knee has been bothering me"],
                "source_bot": "COACH",
            }
        )
        assert result["status"] == "proposal_recorded"
        evidence = collector.memory_proposals[0]["evidence"]
        assert "my knee" in evidence["quotes"][0]


# ---------------------------------------------------------------------------
# Regression: tools must reject calls missing required payload fields
# ---------------------------------------------------------------------------


class TestMissingPayloadRejected:
    """Reproduces the LLM error where 'patch' or 'items' is omitted."""

    def test_profile_patch_without_patch_field_rejected(self) -> None:
        """propose_profile_patch must fail when 'patch' dict is missing."""
        from pydantic import ValidationError

        from app.tools.proposal_tools import ProposeProfilePatchArgs

        with pytest.raises(ValidationError, match="patch"):
            ProposeProfilePatchArgs(
                confidence=1,
                message_ids=[],
                quotes=["after breakfast"],
                source_bot="INTAKE",
            )

    def test_memory_patch_without_items_field_rejected(self) -> None:
        """propose_memory_patch must fail when 'items' list is missing."""
        from pydantic import ValidationError

        from app.tools.proposal_tools import ProposeMemoryPatchArgs

        with pytest.raises(ValidationError, match="items"):
            ProposeMemoryPatchArgs(
                confidence=1,
                message_ids=[],
                quotes=["User prefers nudges at 1 am"],
                source_bot="INTAKE",
            )

    def test_profile_patch_with_patch_field_accepted(self) -> None:
        """Providing 'patch' must succeed."""
        from app.tools.proposal_tools import ProposeProfilePatchArgs

        args = ProposeProfilePatchArgs(
            patch={"prompt_anchor": "after breakfast", "preferred_time": "1am"},
            confidence=1,
            message_ids=[],
            quotes=["after breakfast", "1 am"],
            source_bot="INTAKE",
        )
        assert args.patch["prompt_anchor"] == "after breakfast"

    def test_memory_patch_with_items_field_accepted(self) -> None:
        """Providing 'items' must succeed."""
        from app.tools.proposal_tools import ProposeMemoryPatchArgs

        args = ProposeMemoryPatchArgs(
            items=[{"content": "User prefers nudges at 1 am after breakfast"}],
            confidence=1,
            message_ids=[],
            quotes=["time: 1am; anchor: after breakfast"],
            source_bot="INTAKE",
        )
        assert args.items[0]["content"] == "User prefers nudges at 1 am after breakfast"
