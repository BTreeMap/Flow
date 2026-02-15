"""Tests for the new multi-bot architecture.

Validates:
- Router permission matrix enforcement (Intake vs Feedback vs Coach)
- Confidence threshold behavior
- Evidence span requirements
- Profile schema validation and merge rules
- Memory conservative write rules
- Audit log records proposals and commit decisions
- RouteDecision includes COACH route
- Deterministic routing logic
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.patches import (
    COACH_ALLOWED_FIELDS,
    CONFIDENCE_THRESHOLDS,
    FEEDBACK_ALLOWED_FIELDS,
    INTAKE_ALLOWED_FIELDS,
    EvidenceSpan,
    MemoryItemData,
    MemoryPatchProposal,
    ProfilePatchProposal,
    UserProfileData,
)
from app.schemas.router import RouteDecision
from app.services.profile_service import (
    apply_profile_patch,
    get_allowed_fields,
    validate_memory_patch,
    validate_profile_patch,
)


# ---------------------------------------------------------------------------
# Permission matrix constants
# ---------------------------------------------------------------------------


class TestPermissionMatrix:
    def test_intake_allowed_fields(self) -> None:
        """Intake can only set onboarding fields."""
        assert INTAKE_ALLOWED_FIELDS == {
            "prompt_anchor",
            "preferred_time",
            "habit_domain",
            "motivational_frame",
        }

    def test_feedback_allowed_fields(self) -> None:
        """Feedback can set rolling coaching fields."""
        assert FEEDBACK_ALLOWED_FIELDS == {
            "last_barrier",
            "last_tweak",
            "last_successful_prompt",
            "last_motivator",
            "intensity",
            "tone_tags",
            "tone_scores",
        }

    def test_coach_has_no_direct_fields(self) -> None:
        """Coach can only propose candidates, no direct fields."""
        assert COACH_ALLOWED_FIELDS == set()

    def test_get_allowed_fields_intake(self) -> None:
        assert get_allowed_fields("INTAKE") == INTAKE_ALLOWED_FIELDS

    def test_get_allowed_fields_feedback(self) -> None:
        assert get_allowed_fields("FEEDBACK") == FEEDBACK_ALLOWED_FIELDS

    def test_get_allowed_fields_coach(self) -> None:
        assert get_allowed_fields("COACH") == set()

    def test_get_allowed_fields_unknown(self) -> None:
        assert get_allowed_fields("UNKNOWN") == set()


# ---------------------------------------------------------------------------
# Profile patch validation
# ---------------------------------------------------------------------------


class TestProfilePatchValidation:
    def test_intake_can_set_prompt_anchor(self) -> None:
        proposal = ProfilePatchProposal(
            patch={"prompt_anchor": "after coffee"},
            confidence=0.9,
            evidence=EvidenceSpan(message_ids=[1], quotes=["after coffee"]),
            source_bot="INTAKE",
        )
        valid, reason = validate_profile_patch(proposal, [1, 2, 3])
        assert valid is True

    def test_intake_cannot_set_last_barrier(self) -> None:
        proposal = ProfilePatchProposal(
            patch={"last_barrier": "too tired"},
            confidence=0.9,
            evidence=EvidenceSpan(message_ids=[1]),
            source_bot="INTAKE",
        )
        valid, reason = validate_profile_patch(proposal, [1])
        assert valid is False
        assert "not allowed" in reason

    def test_feedback_can_set_last_barrier(self) -> None:
        proposal = ProfilePatchProposal(
            patch={"last_barrier": "evening fatigue"},
            confidence=0.7,
            evidence=EvidenceSpan(message_ids=[1]),
            source_bot="FEEDBACK",
        )
        valid, reason = validate_profile_patch(proposal, [1])
        assert valid is True

    def test_feedback_cannot_set_prompt_anchor(self) -> None:
        proposal = ProfilePatchProposal(
            patch={"prompt_anchor": "changed"},
            confidence=0.9,
            evidence=EvidenceSpan(message_ids=[1]),
            source_bot="FEEDBACK",
        )
        valid, reason = validate_profile_patch(proposal, [1])
        assert valid is False
        assert "not allowed" in reason

    def test_coach_cannot_set_any_field(self) -> None:
        proposal = ProfilePatchProposal(
            patch={"prompt_anchor": "test"},
            confidence=0.9,
            evidence=EvidenceSpan(message_ids=[1]),
            source_bot="COACH",
        )
        valid, reason = validate_profile_patch(proposal, [1])
        assert valid is False


# ---------------------------------------------------------------------------
# Confidence threshold behavior
# ---------------------------------------------------------------------------


class TestConfidenceThresholds:
    def test_intake_below_threshold_rejected(self) -> None:
        proposal = ProfilePatchProposal(
            patch={"prompt_anchor": "test"},
            confidence=0.3,  # below 0.5 threshold
            evidence=EvidenceSpan(message_ids=[1]),
            source_bot="INTAKE",
        )
        valid, reason = validate_profile_patch(proposal, [1])
        assert valid is False
        assert "Confidence" in reason

    def test_intake_at_threshold_accepted(self) -> None:
        proposal = ProfilePatchProposal(
            patch={"prompt_anchor": "test"},
            confidence=0.5,
            evidence=EvidenceSpan(message_ids=[1]),
            source_bot="INTAKE",
        )
        valid, reason = validate_profile_patch(proposal, [1])
        assert valid is True

    def test_feedback_below_threshold_rejected(self) -> None:
        proposal = ProfilePatchProposal(
            patch={"last_barrier": "test"},
            confidence=0.3,
            evidence=EvidenceSpan(message_ids=[1]),
            source_bot="FEEDBACK",
        )
        valid, reason = validate_profile_patch(proposal, [1])
        assert valid is False

    def test_coach_high_threshold(self) -> None:
        """Coach requires 0.8 confidence (but still rejected since no fields allowed)."""
        assert CONFIDENCE_THRESHOLDS["COACH"] == 0.8


# ---------------------------------------------------------------------------
# Evidence span requirements
# ---------------------------------------------------------------------------


class TestEvidenceSpanRequirements:
    def test_empty_evidence_rejected(self) -> None:
        proposal = ProfilePatchProposal(
            patch={"prompt_anchor": "test"},
            confidence=0.9,
            evidence=EvidenceSpan(message_ids=[]),
            source_bot="INTAKE",
        )
        valid, reason = validate_profile_patch(proposal, [1, 2])
        assert valid is False
        assert "at least one message" in reason

    def test_evidence_from_non_recent_message_rejected(self) -> None:
        proposal = ProfilePatchProposal(
            patch={"prompt_anchor": "test"},
            confidence=0.9,
            evidence=EvidenceSpan(message_ids=[999]),  # not in recent
            source_bot="INTAKE",
        )
        valid, reason = validate_profile_patch(proposal, [1, 2, 3])
        assert valid is False
        assert "not in recent context" in reason

    def test_evidence_from_recent_message_accepted(self) -> None:
        proposal = ProfilePatchProposal(
            patch={"prompt_anchor": "test"},
            confidence=0.9,
            evidence=EvidenceSpan(message_ids=[2], quotes=["I want to..."]),
            source_bot="INTAKE",
        )
        valid, reason = validate_profile_patch(proposal, [1, 2, 3])
        assert valid is True


# ---------------------------------------------------------------------------
# Memory patch validation
# ---------------------------------------------------------------------------


class TestMemoryPatchValidation:
    def test_intake_can_propose_memory(self) -> None:
        proposal = MemoryPatchProposal(
            items=[MemoryItemData(content="User prefers mornings")],
            confidence=0.7,
            evidence=EvidenceSpan(message_ids=[1]),
            source_bot="INTAKE",
        )
        valid, reason = validate_memory_patch(proposal, [1])
        assert valid is True

    def test_feedback_can_propose_memory(self) -> None:
        proposal = MemoryPatchProposal(
            items=[MemoryItemData(content="Recurring barrier: evening fatigue")],
            confidence=0.7,
            evidence=EvidenceSpan(message_ids=[1]),
            source_bot="FEEDBACK",
        )
        valid, reason = validate_memory_patch(proposal, [1])
        assert valid is True

    def test_coach_cannot_write_memory(self) -> None:
        proposal = MemoryPatchProposal(
            items=[MemoryItemData(content="User mentioned pain")],
            confidence=0.9,
            evidence=EvidenceSpan(message_ids=[1]),
            source_bot="COACH",
        )
        valid, reason = validate_memory_patch(proposal, [1])
        assert valid is False
        assert "Coach" in reason

    def test_too_long_memory_item_rejected(self) -> None:
        proposal = MemoryPatchProposal(
            items=[MemoryItemData(content="x" * 501)],
            confidence=0.9,
            evidence=EvidenceSpan(message_ids=[1]),
            source_bot="FEEDBACK",
        )
        valid, reason = validate_memory_patch(proposal, [1])
        assert valid is False
        assert "short" in reason

    def test_memory_evidence_validation(self) -> None:
        proposal = MemoryPatchProposal(
            items=[MemoryItemData(content="test")],
            confidence=0.9,
            evidence=EvidenceSpan(message_ids=[999]),
            source_bot="FEEDBACK",
        )
        valid, reason = validate_memory_patch(proposal, [1, 2])
        assert valid is False
        assert "not in recent context" in reason

    def test_memory_empty_evidence_rejected(self) -> None:
        proposal = MemoryPatchProposal(
            items=[MemoryItemData(content="test")],
            confidence=0.9,
            evidence=EvidenceSpan(message_ids=[]),
            source_bot="FEEDBACK",
        )
        valid, reason = validate_memory_patch(proposal, [1])
        assert valid is False


# ---------------------------------------------------------------------------
# Profile schema validation and merge
# ---------------------------------------------------------------------------


class TestProfileSchemaAndMerge:
    def test_default_profile(self) -> None:
        p = UserProfileData()
        assert p.prompt_anchor == ""
        assert p.preferred_time == ""
        assert p.intensity == "normal"
        assert p.total_prompts == 0

    def test_apply_profile_patch(self) -> None:
        p = UserProfileData()
        updated = apply_profile_patch(p, {"prompt_anchor": "after coffee"})
        assert updated.prompt_anchor == "after coffee"
        assert updated.preferred_time == ""  # unchanged

    def test_apply_profile_patch_multiple_fields(self) -> None:
        p = UserProfileData()
        updated = apply_profile_patch(
            p,
            {
                "prompt_anchor": "after coffee",
                "preferred_time": "8am",
                "habit_domain": "exercise",
            },
        )
        assert updated.prompt_anchor == "after coffee"
        assert updated.preferred_time == "8am"
        assert updated.habit_domain == "exercise"

    def test_apply_profile_patch_preserves_existing(self) -> None:
        p = UserProfileData(prompt_anchor="morning", intensity="high")
        updated = apply_profile_patch(p, {"preferred_time": "9am"})
        assert updated.prompt_anchor == "morning"
        assert updated.intensity == "high"
        assert updated.preferred_time == "9am"

    def test_patch_ignores_unknown_fields(self) -> None:
        p = UserProfileData()
        updated = apply_profile_patch(p, {"unknown_field": "value"})
        assert not hasattr(updated, "unknown_field")

    def test_profile_data_serialization(self) -> None:
        p = UserProfileData(prompt_anchor="test", tone_tags=["concise"])
        json_str = p.model_dump_json()
        restored = UserProfileData.model_validate_json(json_str)
        assert restored.prompt_anchor == "test"
        assert restored.tone_tags == ["concise"]


# ---------------------------------------------------------------------------
# RouteDecision includes COACH
# ---------------------------------------------------------------------------


class TestRouteDecisionCoach:
    def test_coach_route_valid(self) -> None:
        d = RouteDecision(route="COACH")
        assert d.route == "COACH"

    def test_intake_still_valid(self) -> None:
        d = RouteDecision(route="INTAKE")
        assert d.route == "INTAKE"

    def test_feedback_still_valid(self) -> None:
        d = RouteDecision(route="FEEDBACK")
        assert d.route == "FEEDBACK"

    def test_invalid_route_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RouteDecision(route="INVALID")  # type: ignore[arg-type]

    def test_route_decision_fields(self) -> None:
        fields = set(RouteDecision.model_fields.keys())
        assert fields == {"route", "reason"}


# ---------------------------------------------------------------------------
# Deterministic routing
# ---------------------------------------------------------------------------


class TestDeterministicRouting:
    def test_missing_profile_routes_to_intake(self) -> None:
        from app.agents.engine import route_turn_deterministic

        profile = UserProfileData()  # empty
        decision = route_turn_deterministic(profile, "")
        assert decision.route == "INTAKE"

    def test_complete_profile_routes_to_coach(self) -> None:
        from app.agents.engine import route_turn_deterministic

        profile = UserProfileData(
            prompt_anchor="after coffee",
            preferred_time="8am",
        )
        decision = route_turn_deterministic(profile, "")
        assert decision.route == "COACH"

    def test_feedback_state_routes_to_feedback(self) -> None:
        from app.agents.engine import route_turn_deterministic

        profile = UserProfileData(
            prompt_anchor="after coffee",
            preferred_time="8am",
        )
        decision = route_turn_deterministic(profile, "FEEDBACK")
        assert decision.route == "FEEDBACK"

    def test_missing_anchor_overrides_feedback(self) -> None:
        from app.agents.engine import route_turn_deterministic

        profile = UserProfileData(preferred_time="8am")  # missing prompt_anchor
        decision = route_turn_deterministic(profile, "FEEDBACK")
        assert decision.route == "INTAKE"


# ---------------------------------------------------------------------------
# Proposal tools
# ---------------------------------------------------------------------------


class TestProposalTools:
    def test_proposal_collector(self) -> None:
        from app.tools.proposal_tools import ProposalCollector

        collector = ProposalCollector()
        collector.add_profile_proposal({"patch": {"x": 1}})
        collector.add_memory_proposal({"items": [{"content": "test"}]})
        assert len(collector.profile_proposals) == 1
        assert len(collector.memory_proposals) == 1

    def test_make_proposal_tools_creates_two_tools(self) -> None:
        from app.tools.proposal_tools import ProposalCollector, make_proposal_tools

        collector = ProposalCollector()
        tools = make_proposal_tools(collector, "INTAKE")
        names = [t.name for t in tools]
        assert "propose_profile_patch" in names
        assert "propose_memory_patch" in names

    def test_proposal_tool_records_to_collector(self) -> None:
        from app.tools.proposal_tools import ProposalCollector, make_proposal_tools

        collector = ProposalCollector()
        tools = make_proposal_tools(collector, "INTAKE")
        profile_tool = next(t for t in tools if t.name == "propose_profile_patch")
        profile_tool.invoke(
            {
                "patch": {"prompt_anchor": "test"},
                "confidence": 0.9,
                "message_ids": [1],
                "source_bot": "INTAKE",
            }
        )
        assert len(collector.profile_proposals) == 1
        assert collector.profile_proposals[0]["patch"]["prompt_anchor"] == "test"


# ---------------------------------------------------------------------------
# EvidenceSpan model
# ---------------------------------------------------------------------------


class TestEvidenceSpanModel:
    def test_valid_evidence(self) -> None:
        e = EvidenceSpan(message_ids=[1, 2], quotes=["hello"])
        assert e.message_ids == [1, 2]
        assert e.quotes == ["hello"]

    def test_empty_quotes_default(self) -> None:
        e = EvidenceSpan(message_ids=[1])
        assert e.quotes == []

    def test_requires_message_ids(self) -> None:
        with pytest.raises(ValidationError):
            EvidenceSpan()  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# MemoryItemData model
# ---------------------------------------------------------------------------


class TestMemoryItemDataModel:
    def test_valid_item(self) -> None:
        item = MemoryItemData(content="User prefers mornings")
        assert item.content == "User prefers mornings"
        assert item.source_message_ids == []
        assert item.tags == []

    def test_with_sources_and_tags(self) -> None:
        item = MemoryItemData(
            content="Recurring barrier: evening fatigue",
            source_message_ids=[1, 2],
            tags=["barrier"],
        )
        assert item.source_message_ids == [1, 2]
        assert item.tags == ["barrier"]
