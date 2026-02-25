import base64
import re
import secrets
import sys
from unittest.mock import MagicMock
import logging

# Only mock h4ckath0n if it's not already available.
# This prevents breaking CI where h4ckath0n is available and used by other tests.
try:
    from h4ckath0n.auth.passkeys import random_base32  # noqa: F401
except ImportError:
    logging.warning("h4ckath0n not found, mocking it for id_utils tests.")
    m = MagicMock()
    sys.modules["h4ckath0n"] = m
    sys.modules["h4ckath0n.auth"] = m.auth
    sys.modules["h4ckath0n.auth.passkeys"] = m.auth.passkeys
    sys.modules["h4ckath0n.auth.passkeys"].random_base32 = lambda nbytes=20: (
        base64.b32encode(secrets.token_bytes(nbytes))
        .decode("ascii")
        .lower()
        .replace("=", "")
    )


def test_generate_project_id_format():
    """Test that project ID follows the custom scheme: 'p' + 31 lowercase base32 chars."""
    from app.id_utils import generate_project_id

    pid = generate_project_id()
    assert len(pid) == 32
    assert pid.startswith("p")
    # base32 uses a-z and 2-7
    assert re.fullmatch(r"p[a-z2-7]{31}", pid)


def test_generate_server_msg_id_format():
    """Test that server message ID is 36 chars and starts with 'm'."""
    from app.id_utils import generate_server_msg_id

    sid = generate_server_msg_id()
    assert len(sid) == 36
    assert sid.startswith("m")
    assert re.fullmatch(r"m[a-z2-7]{35}", sid)


def test_generate_project_id_uniqueness():
    """Test that generated project IDs are unique."""
    from app.id_utils import generate_project_id

    ids = {generate_project_id() for _ in range(100)}
    assert len(ids) == 100


def test_generate_server_msg_id_uniqueness():
    """Test that generated server message IDs are unique."""
    from app.id_utils import generate_server_msg_id

    ids = {generate_server_msg_id() for _ in range(100)}
    assert len(ids) == 100
