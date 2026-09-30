"""Tests for prompt loading, versioning, and safety invariants."""

from __future__ import annotations

import logging
import re

import pytest
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


class TestPromptResolution:
    """Prompt resolution must survive a stale/mounted prompts directory.

    Production mounts a host ``./prompts`` over ``/app/prompts``; a baked copy
    inside the package must still resolve newly added prompts.
    """

    def test_falls_back_when_primary_dir_missing_file(
        self, tmp_path, monkeypatch
    ) -> None:
        from app import prompt_loader

        # Override dir that exists but lacks the requested prompt.
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        monkeypatch.setenv("FLOW_PROMPTS_DIR", str(empty_dir))
        monkeypatch.setattr(prompt_loader, "_cache", {})

        # Should still resolve via the in-repo fallback candidate dirs.
        text = prompt_loader.load_prompt("router_system")
        assert len(text.strip()) > 0

    def test_override_dir_takes_precedence(self, tmp_path, monkeypatch) -> None:
        from app import prompt_loader

        override_dir = tmp_path / "custom"
        override_dir.mkdir()
        (override_dir / "router_system.txt").write_text("OVERRIDDEN", encoding="utf-8")
        monkeypatch.setenv("FLOW_PROMPTS_DIR", str(override_dir))
        monkeypatch.setattr(prompt_loader, "_cache", {})

        assert prompt_loader.load_prompt("router_system") == "OVERRIDDEN"

    def test_missing_prompt_raises_file_not_found(self, tmp_path, monkeypatch) -> None:
        from app import prompt_loader

        monkeypatch.setattr(prompt_loader, "_cache", {})
        with pytest.raises(FileNotFoundError):
            prompt_loader.load_prompt("does_not_exist_anywhere")


class TestPromptResolutionVisibility:
    """Fallback and missing-file conditions must surface in the logs.

    These tests attach a dedicated handler to the ``app.prompt_loader`` logger
    rather than relying on the root-attached ``caplog`` handler, so they are
    immune to global logging state mutated by other tests (e.g. TestClient
    lifespans reconfiguring logging).
    """

    @staticmethod
    def _attach(level: int) -> tuple[logging.Logger, logging.Handler, list[str], int]:
        from app import prompt_loader

        records: list[str] = []

        class _Collector(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                records.append(record.getMessage())

        handler = _Collector(level)
        target = logging.getLogger(prompt_loader.logger.name)
        target.addHandler(handler)
        target.setLevel(level)
        # A prior ``dictConfig`` with ``disable_existing_loggers=True`` may have
        # set the per-logger ``disabled`` flag, which silences emits regardless
        # of handlers/levels. Re-enable it for the capture.
        target.disabled = False
        # pytest manages a global ``logging.disable`` threshold; tests that do
        # not use the ``caplog`` fixture inherit whatever level a prior test
        # left in place, which can suppress records. Clear it for the duration
        # of the capture and restore it afterwards.
        prior_disable = logging.root.manager.disable
        logging.disable(logging.NOTSET)
        return target, handler, records, prior_disable

    def test_fallback_emits_warning(self, tmp_path, monkeypatch) -> None:
        from app import prompt_loader

        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        monkeypatch.setenv("FLOW_PROMPTS_DIR", str(empty_dir))
        monkeypatch.setattr(prompt_loader, "_cache", {})

        target, handler, records, prior_disable = self._attach(logging.WARNING)
        try:
            prompt_loader.load_prompt("router_system")
        finally:
            target.removeHandler(handler)
            logging.disable(prior_disable)

        assert any(
            "router_system" in msg and "fallback" in msg.lower() for msg in records
        ), f"expected a fallback WARNING mentioning the prompt name; got {records}"

    def test_missing_everywhere_emits_error(self, monkeypatch) -> None:
        from app import prompt_loader

        monkeypatch.setattr(prompt_loader, "_cache", {})

        target, handler, records, prior_disable = self._attach(logging.ERROR)
        try:
            with pytest.raises(FileNotFoundError):
                prompt_loader.load_prompt("does_not_exist_anywhere")
        finally:
            target.removeHandler(handler)
            logging.disable(prior_disable)

        assert any("does_not_exist_anywhere" in msg for msg in records), (
            f"expected an ERROR log before raising FileNotFoundError; got {records}"
        )

    def test_describe_resolution_reports_dirs(self) -> None:
        from app import prompt_loader

        rows = prompt_loader.describe_resolution()
        assert rows, "expected at least one candidate prompt directory"
        assert all(
            isinstance(path, str) and isinstance(exists, bool) for path, exists in rows
        )


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

        assert load_prompt("router_system") == ROUTER_SYSTEM_PROMPT


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
