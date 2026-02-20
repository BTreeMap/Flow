"""ID generation utilities following the custom id scheme."""

from __future__ import annotations

from h4ckath0n.auth.passkeys import random_base32


def generate_project_id() -> str:
    """Return a 32-char project id: 'p' + 31 lowercase base32 chars."""
    raw = random_base32(nbytes=20)
    return "p" + raw[1:]  # 1 + 31 = 32 chars


def generate_server_msg_id() -> str:
    """Return a server-side message ID as a fixed-width string.

    Rationale:
    - The DB column was originally defined as a string of length 36 (UUID-sized),
      and some backends/environments enforce or assume that width.
    - We therefore keep a UUID-like, fixed-width *string* identifier rather than
      switching to a different type or length.

    Format:
    - "msg_" + 32 lowercase base32 chars (36 total), generated via `random_base32`.
    - Opaque, URL-safe, CSPRNG-backed; intended for internal/server use.
    """
    return "msg_" + random_base32(nbytes=20)
