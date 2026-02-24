import sys
import re
from unittest.mock import MagicMock
import secrets
import base64

# Mock h4ckath0n before importing app.id_utils
m = MagicMock()
sys.modules["h4ckath0n"] = m
sys.modules["h4ckath0n.auth"] = m.auth
sys.modules["h4ckath0n.auth.passkeys"] = m.auth.passkeys


def mock_random_base32(nbytes=20):
    data = secrets.token_bytes(nbytes)
    # base32 encoding results in A-Z, 2-7. Lowercase makes it a-z, 2-7.
    return base64.b32encode(data).decode("ascii").lower().replace("=", "")


m.auth.passkeys.random_base32 = mock_random_base32

# Now we can import the utils
# We add api/ to sys.path if needed, but pytest usually handles it if run from api/
from app.id_utils import generate_project_id, generate_server_msg_id  # noqa: E402


def test_generate_project_id_format():
    """Test that project ID follows the custom scheme: 'p' + 31 lowercase base32 chars."""
    pid = generate_project_id()
    assert len(pid) == 32
    assert pid.startswith("p")
    # base32 uses a-z and 2-7
    assert re.fullmatch(r"p[a-z2-7]{31}", pid)


def test_generate_server_msg_id_format():
    """Test that server message ID is 36 chars and starts with 'm'."""
    sid = generate_server_msg_id()
    assert len(sid) == 36
    assert sid.startswith("m")
    assert re.fullmatch(r"m[a-z2-7]{35}", sid)


def test_generate_project_id_uniqueness():
    """Test that generated project IDs are unique."""
    ids = {generate_project_id() for _ in range(100)}
    assert len(ids) == 100


def test_generate_server_msg_id_uniqueness():
    """Test that generated server message IDs are unique."""
    ids = {generate_server_msg_id() for _ in range(100)}
    assert len(ids) == 100
