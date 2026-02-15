"""Tone adaptation logic matching legacy §6 exactly."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.engine.state import ProfileTone

# §6.1 — Tag whitelist
ALL_TAGS: set[str] = {
    # Style
    "concise",
    "detailed",
    "formal",
    "casual",
    "no_emojis",
    "emojis_ok",
    "bullet_points",
    "one_question_at_a_time",
    # Stance
    "warm_supportive",
    "neutral_professional",
    "direct_coach",
    "gentle_coach",
    # Interaction
    "confirm_before_acting",
    "default_actionable",
    "high_autonomy",
}

# §6.2 — Mutually exclusive pairs
MUTUALLY_EXCLUSIVE_PAIRS: list[tuple[str, str]] = [
    ("concise", "detailed"),
    ("formal", "casual"),
    ("direct_coach", "gentle_coach"),
]

# §6.5 — EMA constants
ALPHA: float = 0.15
ACTIVATION_THRESHOLD: float = 0.7
DEACTIVATION_THRESHOLD: float = 0.4
MIN_IMPLICIT_INTERVAL: timedelta = timedelta(minutes=3)


def validate_proposal(
    tags: list[str],
    scores: dict[str, float] | None = None,
) -> tuple[list[str], dict[str, float]]:
    """Validate an LLM-originated tone proposal (§6.4).

    Returns cleaned (tags, scores).
    """
    # 1. Lowercase + trim
    tags = [t.strip().lower() for t in tags]
    # 2. Strip unknown
    tags = [t for t in tags if t in ALL_TAGS]
    # 3. Deduplicate (preserve order)
    seen: set[str] = set()
    deduped: list[str] = []
    for t in tags:
        if t not in seen:
            seen.add(t)
            deduped.append(t)
    tags = deduped

    clean_scores: dict[str, float] = {}
    if scores:
        for k, v in scores.items():
            k_clean = k.strip().lower()
            if k_clean in ALL_TAGS:
                clean_scores[k_clean] = max(0.0, min(1.0, float(v)))

    return tags, clean_scores


def update_profile_tone(
    profile_tone: ProfileTone,
    proposed_tags: list[str],
    source: str,
    confidence: float = 1.0,
    now: datetime | None = None,
) -> ProfileTone:
    """Apply EMA smoothing and hysteresis to profile tone (§6.5).

    Returns a new ProfileTone instance.
    """
    now = now or datetime.now(timezone.utc)
    scores = dict(profile_tone.tone_scores)
    current_tags = set(profile_tone.tone_tags)

    # Rate-limit implicit updates (§6.5)
    if source == "implicit":
        if profile_tone.tone_last_updated_at is not None:
            elapsed = now - profile_tone.tone_last_updated_at
            if elapsed < MIN_IMPLICIT_INTERVAL:
                return profile_tone  # rejected — too soon

    proposed_set = set(proposed_tags)

    if source == "explicit":
        # Explicit: set scores directly
        for tag in proposed_set:
            scores[tag] = 1.0
        # Decay non-observed tags
        for tag in ALL_TAGS:
            if tag not in proposed_set and tag in scores:
                scores[tag] = (1 - ALPHA) * scores[tag]
    else:
        # Implicit: EMA smoothing
        for tag in ALL_TAGS:
            old = scores.get(tag, 0.0)
            if tag in proposed_set:
                scores[tag] = (1 - ALPHA) * old + ALPHA * 1.0
            elif tag in scores:
                scores[tag] = (1 - ALPHA) * old

    # no_emojis overrides emojis_ok (§6.5)
    if scores.get("no_emojis", 0.0) >= ACTIVATION_THRESHOLD:
        if "emojis_ok" in scores and scores["emojis_ok"] >= ACTIVATION_THRESHOLD:
            scores["emojis_ok"] = DEACTIVATION_THRESHOLD - 0.01

    # Mutual exclusion enforcement (§6.2, §6.5)
    for a, b in MUTUALLY_EXCLUSIVE_PAIRS:
        sa = scores.get(a, 0.0)
        sb = scores.get(b, 0.0)
        if sa >= ACTIVATION_THRESHOLD and sb >= ACTIVATION_THRESHOLD:
            if sa >= sb:
                scores[b] = DEACTIVATION_THRESHOLD - 0.01  # 0.39
            else:
                scores[a] = DEACTIVATION_THRESHOLD - 0.01

    # Hysteresis activation / deactivation (§6.5)
    new_tags: set[str] = set()
    for tag in ALL_TAGS:
        s = scores.get(tag, 0.0)
        if s >= ACTIVATION_THRESHOLD:
            new_tags.add(tag)
        elif s <= DEACTIVATION_THRESHOLD:
            pass  # deactivated
        else:
            # Between thresholds — keep current state
            if tag in current_tags:
                new_tags.add(tag)

    return ProfileTone(
        tone_tags=sorted(new_tags),
        tone_scores=scores,
        tone_version=profile_tone.tone_version + 1,
        tone_last_updated_at=now,
        tone_update_source=source,
        tone_override_until=profile_tone.tone_override_until,
    )


def build_tone_guide(profile_tone: ProfileTone) -> str:
    """Build the <TONE POLICY> block injected into LLM context (§6.6).

    Returns empty string if no active tags.
    """
    active = set(profile_tone.tone_tags)
    if not active:
        return ""

    lines: list[str] = ["<TONE POLICY>"]

    # Style rules
    style_rules: list[str] = []
    if "concise" in active:
        style_rules.append("Keep responses concise and to the point.")
    if "detailed" in active:
        style_rules.append("Provide detailed, thorough responses.")
    if "formal" in active:
        style_rules.append("Use formal language and tone.")
    if "casual" in active:
        style_rules.append("Use casual, conversational language.")
    if "no_emojis" in active:
        style_rules.append("Do NOT use emojis.")
    if "emojis_ok" in active:
        style_rules.append("Emojis are welcome where appropriate.")
    if "bullet_points" in active:
        style_rules.append("Use bullet points for lists and structure.")
    if "one_question_at_a_time" in active:
        style_rules.append("Ask only one question at a time.")
    if style_rules:
        lines.append("Style: " + " ".join(style_rules))

    # Stance rules
    stance_tags = active & {
        "warm_supportive",
        "neutral_professional",
        "direct_coach",
        "gentle_coach",
    }
    if stance_tags:
        stance_labels = {
            "warm_supportive": "Adopt a warm, supportive stance.",
            "neutral_professional": "Keep a neutral, professional stance.",
            "direct_coach": "Be a direct, action-oriented coach.",
            "gentle_coach": "Be a gentle, patient coach.",
        }
        stance_parts = [stance_labels[t] for t in sorted(stance_tags)]
        lines.append("Stance: " + " ".join(stance_parts))
    else:
        lines.append("Stance: Keep a neutral, professional stance.")

    # Interaction rules
    interaction_rules: list[str] = []
    if "confirm_before_acting" in active:
        interaction_rules.append("Confirm with the user before taking actions.")
    if "default_actionable" in active:
        interaction_rules.append("Default to actionable suggestions.")
    if "high_autonomy" in active:
        interaction_rules.append("Respect user autonomy; suggest, don't dictate.")
    if interaction_rules:
        lines.append("Interaction: " + " ".join(interaction_rules))

    lines.append("NEVER mirror hostility, sarcasm, insults, or unsafe language.")
    lines.append("</TONE POLICY>")
    return "\n".join(lines)
