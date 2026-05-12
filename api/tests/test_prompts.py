"""Tests for prompt loading, versioning, and safety invariants."""

from __future__ import annotations

import re

from app.prompt_loader import load_prompt, prompt_hash, prompt_version
from app.schemas.patches import UserProfileData

PROMPT_NAMES = [
    "router_system",
    "intake_system",
    "feedback_system",
    "coach_system",
    "prompt_generator_system",
]


# ---------------------------------------------------------------------------
# Loading & caching
# ---------------------------------------------------------------------------


class TestLoadPrompt:
    def test_all_prompts_load_and_non_empty(self) -> None:
        for name in PROMPT_NAMES:
            text = load_prompt(name)
            assert isinstance(text, str), f"{name} did not return str"
            assert len(text.strip()) > 0, f"{name} is empty"


# ---------------------------------------------------------------------------
# Versioning helpers
# ---------------------------------------------------------------------------


class TestPromptHash:
    def test_returns_non_empty_hex(self) -> None:
        h = prompt_hash("router_system")
        assert len(h) > 0
        assert re.fullmatch(r"[0-9a-f]+", h), f"not hex: {h}"


class TestPromptVersion:
    def test_returns_dict_with_expected_keys(self) -> None:
        v = prompt_version("router_system")
        assert isinstance(v, dict)
        assert "prompt_file" in v
        assert "prompt_sha256" in v
        assert v["prompt_file"] == "router_system"
        assert re.fullmatch(r"[0-9a-f]+", v["prompt_sha256"])


# ---------------------------------------------------------------------------
# Safety: specialists instruct only propose_* tools
# ---------------------------------------------------------------------------


class TestProposalToolInstructions:
    def test_intake_mentions_propose(self) -> None:
        text = load_prompt("intake_system")
        assert "propose_profile_patch" in text

    def test_feedback_mentions_propose(self) -> None:
        text = load_prompt("feedback_system")
        assert "propose_profile_patch" in text

    def test_intake_no_direct_writes(self) -> None:
        text = load_prompt("intake_system")
        assert "save_user_profile" not in text

    def test_feedback_no_direct_writes(self) -> None:
        text = load_prompt("feedback_system")
        assert "save_user_profile" not in text


# ---------------------------------------------------------------------------
# Router prompt consistency
# ---------------------------------------------------------------------------


class TestRouterPromptConsistency:
    def test_engine_uses_loaded_prompt(self) -> None:
        from app.agents.engine import ROUTER_SYSTEM_PROMPT

        assert ROUTER_SYSTEM_PROMPT == load_prompt("router_system")


# ---------------------------------------------------------------------------
# Prompt time context placeholders
# ---------------------------------------------------------------------------


class TestPromptTimeContext:
    def test_specialist_prompts_have_time_placeholders(self) -> None:
        for name in ("coach_system", "intake_system", "feedback_system"):
            text = load_prompt(name)
            assert "$current_date" in text, f"{name} missing $current_date"
            assert "$current_time" in text, f"{name} missing $current_time"
            assert "$timezone" in text, f"{name} missing $timezone"

    def test_prompt_generator_has_authoritative_time_guidance(self) -> None:
        text = load_prompt("prompt_generator_system")
        assert "$current_time" in text
        assert "authoritative" in text.lower()


# ---------------------------------------------------------------------------
# Deterministic routing still works with current prompts
# ---------------------------------------------------------------------------


class TestRouterDeterministic:
    def test_empty_profile_routes_intake(self) -> None:
        from app.agents.engine import route_turn_deterministic

        profile = UserProfileData()
        decision = route_turn_deterministic(profile, "IDLE")
        assert decision.route == "INTAKE"

    def test_complete_profile_routes_coach(self) -> None:
        from app.agents.engine import route_turn_deterministic

        profile = UserProfileData(
            prompt_anchor="morning jog",
            preferred_time="08:00",
        )
        decision = route_turn_deterministic(profile, "IDLE")
        assert decision.route == "COACH"
