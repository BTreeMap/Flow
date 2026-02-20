"""ID generation utilities following the custom id scheme."""

from __future__ import annotations

import uuid
from h4ckath0n.auth.passkeys import random_base32


def generate_project_id() -> str:
    """Return a 32-char project id: 'p' + 31 lowercase base32 chars."""
    raw = random_base32(nbytes=20)
    return "p" + raw[1:]  # 1 + 31 = 32 chars


def generate_server_msg_id() -> str:
    """Return a UUID4 string for server-side message identification."""
    return str(uuid.uuid4())
