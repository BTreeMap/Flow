"""Tests for LangChain agent definitions and canonical engine pipeline.

Validates:
- Proposal tools are available for each specialist
- Router deterministic routing in the canonical engine
- Prompt loading from files works correctly
"""

from __future__ import annotations

from app.agents.engine import (
    _build_profile_summary,
    _build_memory_summary,
    route_turn_deterministic,
)
from app.schemas.patches import UserProfileData, MemoryItemData
from app.tools.proposal_tools import ProposalCollector, make_proposal_tools


# ---------------------------------------------------------------------------
# Proposal tool permissions
# ---------------------------------------------------------------------------


class TestAgentToolPermissions:
    def test_proposal_tools_created(self) -> None:
        collector = ProposalCollector()
        tools = make_proposal_tools(collector, source_bot="INTAKE")
        names = {t.name for t in tools}
        assert names == {
            "propose_profile_patch",
            "propose_memory_patch",
            "propose_schedule_nudge",
            "propose_delete_schedule",
        }

    def test_proposal_tools_for_coach(self) -> None:
        collector = ProposalCollector()
        tools = make_proposal_tools(collector, source_bot="COACH")
        names = {t.name for t in tools}
        assert names == {
            "propose_profile_patch",
            "propose_memory_patch",
            "propose_schedule_nudge",
            "propose_delete_schedule",
        }

    def test_proposal_tools_for_feedback(self) -> None:
        collector = ProposalCollector()
        tools = make_proposal_tools(collector, source_bot="FEEDBACK")
        names = {t.name for t in tools}
        assert names == {
            "propose_profile_patch",
            "propose_memory_patch",
            "propose_schedule_nudge",
            "propose_delete_schedule",
        }


# ---------------------------------------------------------------------------
# Deterministic routing (canonical engine)
# ---------------------------------------------------------------------------


class TestSubStateHelper:
    def test_empty_profile_routes_to_intake(self) -> None:
        profile = UserProfileData()
        decision = route_turn_deterministic(profile, "")
        assert decision.route == "INTAKE"

    def test_feedback_state(self) -> None:
        profile = UserProfileData(prompt_anchor="coffee", preferred_time="8am")
        decision = route_turn_deterministic(profile, "FEEDBACK")
        assert decision.route == "FEEDBACK"

    def test_unknown_state_defaults_to_coach(self) -> None:
        profile = UserProfileData(prompt_anchor="coffee", preferred_time="8am")
        decision = route_turn_deterministic(profile, "BOGUS")
        assert decision.route == "COACH"


# ---------------------------------------------------------------------------
# Profile and memory summary helpers
# ---------------------------------------------------------------------------


class TestSummaryHelpers:
    def test_profile_summary_missing_fields(self) -> None:
        profile = UserProfileData()
        summary = _build_profile_summary(profile)
        assert "missing" in summary

    def test_profile_summary_set_fields(self) -> None:
        profile = UserProfileData(prompt_anchor="coffee", preferred_time="8am")
        summary = _build_profile_summary(profile)
        assert "PromptAnchor=set" in summary
        assert "PreferredTime=set" in summary

    def test_memory_summary_empty(self) -> None:
        summary = _build_memory_summary([])
        assert "No memory" in summary

    def test_memory_summary_with_items(self) -> None:
        items = [
            MemoryItemData(content="User prefers mornings"),
            MemoryItemData(content="Evening fatigue is recurring"),
        ]
        summary = _build_memory_summary(items)
        assert "prefers mornings" in summary
        assert "Evening fatigue" in summary


# ---------------------------------------------------------------------------
# Route decision validation
# ---------------------------------------------------------------------------


class TestRouteDecisionReturned:
    def test_route_decision_for_empty_profile(self) -> None:
        profile = UserProfileData()
        decision = route_turn_deterministic(profile, "")
        assert decision.route == "INTAKE"
        assert hasattr(decision, "reason")

    def test_route_decision_for_complete_profile(self) -> None:
        profile = UserProfileData(prompt_anchor="coffee", preferred_time="8am")
        decision = route_turn_deterministic(profile, "")
        assert decision.route == "COACH"
        assert hasattr(decision, "reason")
