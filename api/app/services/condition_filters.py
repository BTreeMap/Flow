"""Shared text filters that enforce experimental-condition guardrails.

Centralizing the regex here keeps the Coach (chat turn) and the notification
worker (nudge generation) in sync about what counts as forbidden
"psychological framing" in Condition C output.
"""

from __future__ import annotations

import re

# Forbidden patterns for Condition C (LLM adaptation, strictly NO framing).
#
# We reject:
#   * "If/when X, then I/you will Y" implementation intentions
#   * Commitment / self-betting language (commit, contract, promise, bet,
#     reward yourself, I'll reward, …)
#
# The pattern is intentionally case-insensitive and tolerates extra words
# between "if/when" and "then". It is designed to fire on the rewrites the
# audit flagged as the main contamination risk while accepting normal
# encouragement text.
CONDITION_C_FRAMING_PATTERN = re.compile(
    r"(?i)"
    # implementation intention: "if/when ... then ... will"
    r"(\b(?:if|when)\b[^.!?\n]{0,80}\bthen\b[^.!?\n]{0,80}\b(?:i|you|we)?\s*will\b)"
    r"|"
    # commitment / self-betting vocabulary
    r"(\bcommitment\s+contract\b)"
    r"|(\bi\s+(?:will\s+)?bet\b)"
    r"|(\bi\s+promise\b)"
    r"|(\breward\s+yourself\b)"
    r"|(\bi[' ]?ll\s+reward\b)"
    r"|(\bi\s+commit\s+to\b)"
)


def contains_condition_c_framing(text: str) -> bool:
    """Return True if ``text`` contains psychological-framing language forbidden in Condition C."""
    if not text:
        return False
    return bool(CONDITION_C_FRAMING_PATTERN.search(text))
