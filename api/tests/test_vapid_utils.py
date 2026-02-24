import pytest
from app import vapid_utils


@pytest.fixture(autouse=True)
def clear_cache():
    vapid_utils.clear_vapid_cache()
    yield
    vapid_utils.clear_vapid_cache()


def test_get_vapid_public_key(monkeypatch):
    monkeypatch.delenv("VAPID_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("FLOW_VAPID_PUBLIC_KEY", raising=False)
    assert vapid_utils.get_vapid_public_key() == ""

    monkeypatch.setenv("VAPID_PUBLIC_KEY", "test_pub")
    vapid_utils.clear_vapid_cache()
    assert vapid_utils.get_vapid_public_key() == "test_pub"

    monkeypatch.delenv("VAPID_PUBLIC_KEY")
    monkeypatch.setenv("FLOW_VAPID_PUBLIC_KEY", "flow_pub")
    vapid_utils.clear_vapid_cache()
    assert vapid_utils.get_vapid_public_key() == "flow_pub"


def test_get_vapid_private_key(monkeypatch):
    monkeypatch.delenv("VAPID_PRIVATE_KEY", raising=False)
    monkeypatch.delenv("FLOW_VAPID_PRIVATE_KEY", raising=False)
    assert vapid_utils.get_vapid_private_key() == ""

    monkeypatch.setenv("VAPID_PRIVATE_KEY", "test_priv")
    vapid_utils.clear_vapid_cache()
    assert vapid_utils.get_vapid_private_key() == "test_priv"

    monkeypatch.delenv("VAPID_PRIVATE_KEY")
    monkeypatch.setenv("FLOW_VAPID_PRIVATE_KEY", "flow_priv")
    vapid_utils.clear_vapid_cache()
    assert vapid_utils.get_vapid_private_key() == "flow_priv"


def test_get_vapid_sub(monkeypatch):
    monkeypatch.delenv("VAPID_CLAIM_SUB", raising=False)
    assert vapid_utils.get_vapid_sub() == "mailto:flow@oss.joefang.org"

    monkeypatch.setenv("VAPID_CLAIM_SUB", "mailto:test@example.com")
    vapid_utils.clear_vapid_cache()
    assert vapid_utils.get_vapid_sub() == "mailto:test@example.com"


def test_get_vapid_claims(monkeypatch):
    monkeypatch.setenv("VAPID_CLAIM_SUB", "mailto:test@example.com")
    vapid_utils.clear_vapid_cache()
    assert vapid_utils.get_vapid_claims() == {"sub": "mailto:test@example.com"}
