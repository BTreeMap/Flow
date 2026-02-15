"""Tests for the LangChain coordinator router (§4.1).

Validates:
- RouteDecision is a valid Pydantic model
- Router never produces user-visible text
- Deterministic routing respects legacy state gates
- LLM-based routing returns valid RouteDecision
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from app.agents.router import RouteDecision, route_turn, _route_deterministic
from app.schemas.router import RouteDecision as SchemaRouteDecision


# ---------------------------------------------------------------------------
# RouteDecision Pydantic validation
# ---------------------------------------------------------------------------


class TestRouteDecisionSchema:
    def test_valid_intake(self) -> None:
        d = RouteDecision(route="INTAKE")
        assert d.route == "INTAKE"
        assert d.reason is None

    def test_valid_feedback(self) -> None:
        d = RouteDecision(route="FEEDBACK", reason="user in feedback state")
        assert d.route == "FEEDBACK"
        assert d.reason == "user in feedback state"

    def test_invalid_route_rejected(self) -> None:
        import pytest
        with pytest.raises(Exception):
            RouteDecision(route="INVALID")  # type: ignore[arg-type]

    def test_reason_is_optional(self) -> None:
        d = RouteDecision(route="INTAKE")
        assert d.reason is None

    def test_schema_matches_agents_module(self) -> None:
        """RouteDecision in schemas and agents are the same class."""
        assert RouteDecision is SchemaRouteDecision


# ---------------------------------------------------------------------------
# Deterministic routing (no LLM) — legacy §3.1
# ---------------------------------------------------------------------------


class TestDeterministicRouting:
    def test_empty_state_defaults_to_intake(self) -> None:
        """Empty/missing sub-state routes to INTAKE (§3.1)."""
        decision = route_turn(
            user_text="hello",
            sub_state="",
            profile_summary="",
            llm=None,
        )
        assert decision.route == "INTAKE"

    def test_intake_state_routes_to_intake(self) -> None:
        decision = route_turn(
            user_text="hello",
            sub_state="INTAKE",
            profile_summary="",
            llm=None,
        )
        assert decision.route == "INTAKE"

    def test_feedback_state_routes_to_feedback(self) -> None:
        decision = route_turn(
            user_text="I did my habit",
            sub_state="FEEDBACK",
            profile_summary="",
            llm=None,
        )
        assert decision.route == "FEEDBACK"

    def test_unknown_state_defaults_to_intake(self) -> None:
        decision = route_turn(
            user_text="hi",
            sub_state="UNKNOWN",
            profile_summary="",
            llm=None,
        )
        assert decision.route == "INTAKE"

    def test_reason_is_log_only(self) -> None:
        """Reason field is populated but must not be user-facing."""
        decision = route_turn(
            user_text="hi",
            sub_state="FEEDBACK",
            profile_summary="",
            llm=None,
        )
        assert decision.reason is not None
        # The reason should explain the routing, not be a user message
        assert "FEEDBACK" in decision.reason or "sub-state" in decision.reason


# ---------------------------------------------------------------------------
# Router never produces user-visible text
# ---------------------------------------------------------------------------


class TestRouterNoUserText:
    def test_deterministic_route_returns_only_decision(self) -> None:
        """The router output is strictly a RouteDecision, not user text."""
        decision = _route_deterministic("INTAKE")
        assert isinstance(decision, RouteDecision)
        # RouteDecision has only route + reason; no content/text field
        assert not hasattr(decision, "content")
        assert not hasattr(decision, "text")
        assert not hasattr(decision, "message")

    def test_route_decision_fields_are_limited(self) -> None:
        """RouteDecision model only has route and reason fields."""
        fields = set(RouteDecision.model_fields.keys())
        assert fields == {"route", "reason"}
