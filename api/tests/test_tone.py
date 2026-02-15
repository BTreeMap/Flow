"""Tests for tone adaptation logic (§6)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.engine.state import ProfileTone
from app.engine.tone import (
    ACTIVATION_THRESHOLD,
    DEACTIVATION_THRESHOLD,
    build_tone_guide,
    update_profile_tone,
    validate_proposal,
)


# ---------------------------------------------------------------------------
# §6.1 / §6.4 — Tag whitelist validation
# ---------------------------------------------------------------------------


class TestValidateProposal:
    def test_unknown_tags_stripped(self) -> None:
        tags, scores = validate_proposal(["concise", "UNKNOWN_TAG", "bogus"])
        assert tags == ["concise"]
        assert "UNKNOWN_TAG" not in tags

    def test_known_tags_preserved(self) -> None:
        tags, _ = validate_proposal(["concise", "formal", "warm_supportive"])
        assert tags == ["concise", "formal", "warm_supportive"]

    def test_case_insensitive(self) -> None:
        tags, _ = validate_proposal(["CONCISE", "Formal"])
        assert tags == ["concise", "formal"]

    def test_deduplication(self) -> None:
        tags, _ = validate_proposal(["concise", "concise", "formal"])
        assert tags == ["concise", "formal"]

    def test_scores_clamped(self) -> None:
        _, scores = validate_proposal([], {"concise": 1.5, "formal": -0.3})
        assert scores["concise"] == 1.0
        assert scores["formal"] == 0.0

    def test_unknown_score_keys_stripped(self) -> None:
        _, scores = validate_proposal([], {"bogus": 0.5, "concise": 0.8})
        assert "bogus" not in scores
        assert scores["concise"] == 0.8


# ---------------------------------------------------------------------------
# §6.5 — EMA smoothing
# ---------------------------------------------------------------------------


class TestEMASmoothing:
    def test_explicit_sets_score_directly(self) -> None:
        tone = ProfileTone()
        result = update_profile_tone(tone, ["concise"], source="explicit")
        assert result.tone_scores["concise"] == 1.0

    def test_implicit_applies_ema(self) -> None:
        tone = ProfileTone(tone_scores={"concise": 0.8})
        result = update_profile_tone(tone, ["concise"], source="implicit")
        expected = (1 - 0.15) * 0.8 + 0.15 * 1.0
        assert abs(result.tone_scores["concise"] - expected) < 1e-9

    def test_implicit_decays_non_observed(self) -> None:
        tone = ProfileTone(tone_scores={"concise": 0.8})
        result = update_profile_tone(tone, ["formal"], source="implicit")
        expected_concise = (1 - 0.15) * 0.8
        assert abs(result.tone_scores["concise"] - expected_concise) < 1e-9

    def test_explicit_decays_non_observed(self) -> None:
        tone = ProfileTone(tone_scores={"concise": 0.5})
        result = update_profile_tone(tone, ["formal"], source="explicit")
        expected_concise = (1 - 0.15) * 0.5
        assert abs(result.tone_scores["concise"] - expected_concise) < 1e-9

    def test_version_increments(self) -> None:
        tone = ProfileTone(tone_version=3)
        result = update_profile_tone(tone, ["concise"], source="explicit")
        assert result.tone_version == 4


# ---------------------------------------------------------------------------
# §6.5 — Rate limiting (implicit updates within 3 minutes rejected)
# ---------------------------------------------------------------------------


class TestRateLimiting:
    def test_implicit_rejected_within_3_minutes(self) -> None:
        now = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        tone = ProfileTone(
            tone_scores={"concise": 0.5},
            tone_last_updated_at=now - timedelta(minutes=2),
        )
        result = update_profile_tone(
            tone, ["concise"], source="implicit", now=now
        )
        # Should be rejected — returned unchanged
        assert result is tone

    def test_implicit_accepted_after_3_minutes(self) -> None:
        now = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        tone = ProfileTone(
            tone_scores={"concise": 0.5},
            tone_last_updated_at=now - timedelta(minutes=4),
        )
        result = update_profile_tone(
            tone, ["concise"], source="implicit", now=now
        )
        assert result is not tone
        assert result.tone_version == tone.tone_version + 1

    def test_explicit_ignores_rate_limit(self) -> None:
        now = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        tone = ProfileTone(
            tone_scores={"concise": 0.5},
            tone_last_updated_at=now - timedelta(minutes=1),
        )
        result = update_profile_tone(
            tone, ["concise"], source="explicit", now=now
        )
        assert result is not tone
        assert result.tone_scores["concise"] == 1.0


# ---------------------------------------------------------------------------
# §6.2, §6.5 — Mutual exclusion enforcement
# ---------------------------------------------------------------------------


class TestMutualExclusion:
    def test_concise_vs_detailed(self) -> None:
        tone = ProfileTone()
        result = update_profile_tone(
            tone, ["concise", "detailed"], source="explicit"
        )
        # Both set to 1.0, but mutual exclusion kicks in.
        # concise == detailed == 1.0, so the first in pair wins (concise >= detailed)
        assert result.tone_scores["concise"] == 1.0
        assert result.tone_scores["detailed"] < ACTIVATION_THRESHOLD

    def test_formal_vs_casual(self) -> None:
        tone = ProfileTone()
        result = update_profile_tone(
            tone, ["formal", "casual"], source="explicit"
        )
        assert result.tone_scores["formal"] == 1.0
        assert result.tone_scores["casual"] < ACTIVATION_THRESHOLD

    def test_direct_coach_vs_gentle_coach(self) -> None:
        tone = ProfileTone()
        result = update_profile_tone(
            tone, ["direct_coach", "gentle_coach"], source="explicit"
        )
        assert result.tone_scores["direct_coach"] == 1.0
        assert result.tone_scores["gentle_coach"] < ACTIVATION_THRESHOLD


# ---------------------------------------------------------------------------
# §6.5 — Activation / deactivation hysteresis
# ---------------------------------------------------------------------------


class TestHysteresis:
    def test_activation_at_threshold(self) -> None:
        tone = ProfileTone(tone_scores={"concise": ACTIVATION_THRESHOLD})
        result = update_profile_tone(tone, [], source="explicit")
        # Decay: (1-0.15)*0.7 = 0.595 — between thresholds, was active → stays active
        # But concise was not in tone_tags, so it's not "currently active"
        assert "concise" not in result.tone_tags or result.tone_scores["concise"] >= ACTIVATION_THRESHOLD

    def test_deactivation_below_threshold(self) -> None:
        tone = ProfileTone(
            tone_tags=["concise"],
            tone_scores={"concise": DEACTIVATION_THRESHOLD - 0.01},
        )
        result = update_profile_tone(tone, [], source="explicit")
        assert "concise" not in result.tone_tags

    def test_between_thresholds_keeps_current_state(self) -> None:
        """Tag between 0.4 and 0.7 keeps its current activation state."""
        tone = ProfileTone(
            tone_tags=["concise"],
            tone_scores={"concise": 0.55},
        )
        result = update_profile_tone(tone, [], source="explicit")
        # Score decays to (1-0.15)*0.55 = 0.4675, still between thresholds
        # Was active → stays active
        assert "concise" in result.tone_tags

    def test_between_thresholds_inactive_stays_inactive(self) -> None:
        tone = ProfileTone(
            tone_tags=[],
            tone_scores={"concise": 0.55},
        )
        result = update_profile_tone(tone, [], source="explicit")
        assert "concise" not in result.tone_tags


# ---------------------------------------------------------------------------
# §6.5 — no_emojis overrides emojis_ok
# ---------------------------------------------------------------------------


class TestNoEmojisOverride:
    def test_no_emojis_suppresses_emojis_ok(self) -> None:
        tone = ProfileTone()
        result = update_profile_tone(
            tone, ["no_emojis", "emojis_ok"], source="explicit"
        )
        assert "no_emojis" in result.tone_tags
        assert "emojis_ok" not in result.tone_tags
        assert result.tone_scores["emojis_ok"] < ACTIVATION_THRESHOLD


# ---------------------------------------------------------------------------
# §6.6 — build_tone_guide output
# ---------------------------------------------------------------------------


class TestBuildToneGuide:
    def test_empty_tags_returns_empty(self) -> None:
        tone = ProfileTone(tone_tags=[])
        assert build_tone_guide(tone) == ""

    def test_contains_tone_policy_markers(self) -> None:
        tone = ProfileTone(tone_tags=["concise"])
        guide = build_tone_guide(tone)
        assert guide.startswith("<TONE POLICY>")
        assert guide.endswith("</TONE POLICY>")

    def test_concise_style_rule(self) -> None:
        tone = ProfileTone(tone_tags=["concise"])
        guide = build_tone_guide(tone)
        assert "concise" in guide.lower()

    def test_no_emojis_rule(self) -> None:
        tone = ProfileTone(tone_tags=["no_emojis"])
        guide = build_tone_guide(tone)
        assert "Do NOT use emojis" in guide

    def test_stance_included(self) -> None:
        tone = ProfileTone(tone_tags=["warm_supportive"])
        guide = build_tone_guide(tone)
        assert "warm, supportive" in guide.lower()

    def test_default_neutral_stance_when_no_stance_tags(self) -> None:
        tone = ProfileTone(tone_tags=["concise"])
        guide = build_tone_guide(tone)
        assert "neutral, professional" in guide.lower()

    def test_hostility_warning_always_present(self) -> None:
        tone = ProfileTone(tone_tags=["concise"])
        guide = build_tone_guide(tone)
        assert "NEVER mirror hostility" in guide
