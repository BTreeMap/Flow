"""Unit tests for the shared Web Push wire-call service."""

import json

import pytest
import pywebpush
from app.config import clear_config_cache
from app.services import push_service


@pytest.fixture(autouse=True)
def _vapid_env(monkeypatch):
    monkeypatch.setenv("VAPID_PUBLIC_KEY", "public")
    monkeypatch.setenv("VAPID_PRIVATE_KEY", "private")
    monkeypatch.setenv("VAPID_CLAIM_SUB", "mailto:test@example.com")
    clear_config_cache()
    yield
    clear_config_cache()


@pytest.mark.asyncio
async def test_send_webpush_passes_subscription_and_vapid(monkeypatch):
    captured: dict[str, object] = {}

    def fake_webpush(**kwargs):
        captured.update(kwargs)
        return "ok"

    monkeypatch.setattr(pywebpush, "webpush", fake_webpush)

    payload = json.dumps({"title": "hi", "body": "there"})
    await push_service.send_webpush(
        endpoint="https://push.example/abc",
        p256dh="p256dh-key",
        auth="auth-secret",
        payload=payload,
    )

    assert captured["subscription_info"] == {
        "endpoint": "https://push.example/abc",
        "keys": {"p256dh": "p256dh-key", "auth": "auth-secret"},
    }
    assert captured["data"] == payload
    assert captured["vapid_private_key"] == "private"
    assert captured["vapid_claims"] == {"sub": "mailto:test@example.com"}


@pytest.mark.asyncio
async def test_send_webpush_propagates_webpush_exception(monkeypatch):
    def boom(**_kwargs):
        raise pywebpush.WebPushException("gone")

    monkeypatch.setattr(pywebpush, "webpush", boom)

    with pytest.raises(pywebpush.WebPushException):
        await push_service.send_webpush(
            endpoint="e", p256dh="p", auth="a", payload="{}"
        )


@pytest.mark.asyncio
async def test_send_webpush_resolves_patch_at_call_time(monkeypatch):
    """The service must look up ``pywebpush.webpush`` at call time so callers and
    tests can patch the symbol after import."""
    calls: list[str] = []

    def patched(**_kwargs):
        calls.append("called")
        return "ok"

    monkeypatch.setattr(pywebpush, "webpush", patched)

    await push_service.send_webpush(endpoint="e", p256dh="p", auth="a", payload="{}")

    assert calls == ["called"]
