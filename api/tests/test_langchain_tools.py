"""Tests for LangChain proposal tools (new architecture).

Validates:
- Proposal tools have Pydantic args_schema
- Proposal tools record proposals to the collector
- Proposal tools return structured results
"""

from __future__ import annotations

from typing import Any

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
    def test_proposal_tools_have_two_tools(self) -> None:
        collector = ProposalCollector()
        tools = make_proposal_tools(collector, source_bot="INTAKE")
        names = sorted(t.name for t in tools)
        assert names == ["propose_memory_patch", "propose_profile_patch"]

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
