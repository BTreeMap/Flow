"""ID generation utilities following the custom id scheme."""

from __future__ import annotations

import base64
import os
import uuid


def generate_project_id() -> str:
    """Return a 32-char project id: 'p' + 31 lowercase base32 chars."""
    raw = base64.b32encode(os.urandom(20)).decode("ascii").lower()
    return "p" + raw[1:]  # 1 + 31 = 32 chars


def generate_server_msg_id() -> str:
    """Return a UUID4 string for server-side message identification."""
    return str(uuid.uuid4())
