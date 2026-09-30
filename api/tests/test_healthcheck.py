"""Tests for the role-agnostic container healthcheck.

The API and worker share one image and one baked ``HEALTHCHECK``. The probe is
healthy if EITHER ``GET /healthz`` returns 2xx OR a fresh worker heartbeat file
exists — no ``FLOW_ROLE`` flag, so old deployments keep working. The heartbeat
path is patched to a tmp file so tests never touch a real shared volume.
"""

from __future__ import annotations

import os
import time
from collections.abc import Iterator

import pytest
from app import config, healthcheck


class _FakeResponse:
    """Minimal context manager mimicking ``urllib.request.urlopen``'s result.

    The ``with`` protocol resolves ``__enter__``/``__exit__`` on the *type*, so
    these must be real methods (not instance attributes) to be picked up.
    """

    def __init__(self, status: int) -> None:
        self.status = status

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


@pytest.fixture(autouse=True)
def _clear_config_cache() -> Iterator[None]:
    config.clear_config_cache()
    yield
    config.clear_config_cache()


@pytest.fixture
def _heartbeat(monkeypatch: pytest.MonkeyPatch, tmp_path) -> str:
    """Point the heartbeat at an isolated tmp file (no real volume touched)."""
    path = str(tmp_path / "flow-worker.heartbeat")
    monkeypatch.setattr(healthcheck, "HEARTBEAT_PATH", path)
    return path


def _no_healthz(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the /healthz probe fail (nothing listening)."""

    def _boom(*a, **k):
        raise OSError("connection refused")

    monkeypatch.setattr(healthcheck.urllib.request, "urlopen", _boom)


def _healthz_status(monkeypatch: pytest.MonkeyPatch, status: int) -> None:
    """Make the /healthz probe return *status*."""
    monkeypatch.setattr(
        healthcheck.urllib.request, "urlopen", lambda *a, **k: _FakeResponse(status)
    )


class TestHeartbeatSignal:
    def test_fresh_heartbeat_alone_is_healthy(
        self, monkeypatch: pytest.MonkeyPatch, _heartbeat: str
    ) -> None:
        # No HTTP server, but a fresh heartbeat → healthy (worker container).
        _no_healthz(monkeypatch)
        with open(_heartbeat, "w", encoding="utf-8") as fh:
            fh.write("now")
        assert healthcheck.main() == 0

    def test_stale_heartbeat_without_api_is_unhealthy(
        self, monkeypatch: pytest.MonkeyPatch, _heartbeat: str
    ) -> None:
        _no_healthz(monkeypatch)
        with open(_heartbeat, "w", encoding="utf-8") as fh:
            fh.write("old")
        old = time.time() - (healthcheck.HEARTBEAT_MAX_AGE_S + 30)
        os.utime(_heartbeat, (old, old))
        assert healthcheck.main() == 1

    def test_missing_heartbeat_without_api_is_unhealthy(
        self, monkeypatch: pytest.MonkeyPatch, _heartbeat: str
    ) -> None:
        _no_healthz(monkeypatch)
        assert healthcheck.main() == 1


class TestApiSignal:
    def test_healthz_2xx_alone_is_healthy(
        self, monkeypatch: pytest.MonkeyPatch, _heartbeat: str
    ) -> None:
        # No heartbeat (API container), but /healthz is 2xx → healthy.
        _healthz_status(monkeypatch, 200)
        assert healthcheck.main() == 0

    def test_healthz_5xx_without_heartbeat_is_unhealthy(
        self, monkeypatch: pytest.MonkeyPatch, _heartbeat: str
    ) -> None:
        _healthz_status(monkeypatch, 503)
        assert healthcheck.main() == 1

    def test_connection_error_without_heartbeat_is_unhealthy(
        self, monkeypatch: pytest.MonkeyPatch, _heartbeat: str
    ) -> None:
        _no_healthz(monkeypatch)
        assert healthcheck.main() == 1


def test_heartbeat_path_is_not_on_shared_data_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """The heartbeat must never live under the shared FLOW_DATA_DIR volume."""
    monkeypatch.setenv("FLOW_DATA_DIR", str(tmp_path))
    config.clear_config_cache()
    assert not healthcheck.HEARTBEAT_PATH.startswith(config.get_data_dir())
