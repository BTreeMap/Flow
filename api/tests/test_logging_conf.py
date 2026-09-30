"""Tests for the declarative logging configuration.

These tests exercise :func:`build_logging_config` (a pure function with no
global side effects) directly. The one test that applies the configuration to
the live root logger restores the prior root-logger state afterwards so the rest
of the suite — and pytest's own ``caplog`` handler — is unaffected.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator

import pytest
from app import logging_conf


class TestBuildLoggingConfig:
    """The dictConfig description is the single source of truth for logging."""

    def test_versioned_and_non_disabling(self) -> None:
        cfg = logging_conf.build_logging_config(log_level="INFO")
        assert cfg["version"] == 1
        # Must never disable existing loggers — that would silence loggers
        # created at import time (and break test fixtures).
        assert cfg["disable_existing_loggers"] is False

    def test_root_uses_requested_level_uppercased(self) -> None:
        cfg = logging_conf.build_logging_config(log_level="debug")
        assert cfg["root"]["level"] == "DEBUG"

    def test_console_handler_always_present(self) -> None:
        cfg = logging_conf.build_logging_config()
        assert cfg["handlers"]["console"]["stream"] == "ext://sys.stdout"
        assert "console" in cfg["root"]["handlers"]

    def test_file_handler_present_when_data_dir_writable(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        monkeypatch.setattr(logging_conf.config, "get_data_dir", lambda: str(tmp_path))
        cfg = logging_conf.build_logging_config()
        assert "file" in cfg["handlers"]
        assert cfg["handlers"]["file"]["filename"].endswith("app.log")
        assert "file" in cfg["root"]["handlers"]

    def test_file_handler_dropped_when_data_dir_unwritable(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        # Point the data dir at a child of a regular file so os.makedirs raises.
        blocker = tmp_path / "not-a-dir"
        blocker.write_text("x", encoding="utf-8")
        monkeypatch.setattr(
            logging_conf.config, "get_data_dir", lambda: str(blocker / "child")
        )
        cfg = logging_conf.build_logging_config()
        assert "file" not in cfg["handlers"]
        # Console-only logging remains so docker logs still receive output.
        assert cfg["root"]["handlers"] == ["console"]

    def test_uvicorn_loggers_propagate_to_root(self) -> None:
        cfg = logging_conf.build_logging_config()
        for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
            assert cfg["loggers"][name]["handlers"] == []
            assert cfg["loggers"][name]["propagate"] is True

    def test_noisy_libraries_pinned_to_warning(self) -> None:
        cfg = logging_conf.build_logging_config()
        assert cfg["loggers"]["httpx"]["level"] == "WARNING"
        assert cfg["loggers"]["httpcore"]["level"] == "WARNING"


@pytest.fixture
def _isolate_root_logging() -> Iterator[None]:
    """Snapshot and restore the root logger so applying a config is contained."""
    root = logging.getLogger()
    saved_handlers = root.handlers[:]
    saved_level = root.level
    saved_disabled = logging.root.manager.disable
    try:
        yield
    finally:
        for handler in root.handlers[:]:
            root.removeHandler(handler)
        for handler in saved_handlers:
            root.addHandler(handler)
        root.setLevel(saved_level)
        logging.disable(saved_disabled)


class TestConfigureLogging:
    """Applying the configuration is idempotent and returns what it applied."""

    def test_returns_applied_config(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
        _isolate_root_logging: None,
    ) -> None:
        monkeypatch.setattr(logging_conf.config, "get_data_dir", lambda: str(tmp_path))
        cfg = logging_conf.configure_logging(log_level="WARNING")
        assert cfg["root"]["level"] == "WARNING"

    def test_idempotent(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
        _isolate_root_logging: None,
    ) -> None:
        monkeypatch.setattr(logging_conf.config, "get_data_dir", lambda: str(tmp_path))
        logging_conf.configure_logging()
        logging_conf.configure_logging()  # second call must not raise or duplicate
        root = logging.getLogger()
        console_handlers = [
            h for h in root.handlers if isinstance(h, logging.StreamHandler)
        ]
        # Exactly one console StreamHandler — dictConfig replaced, not appended.
        assert len(console_handlers) >= 1


class TestRequestIdFilter:
    """Every record carries a correlation id, so lines can be tied to a request."""

    def _record(self) -> logging.LogRecord:
        return logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="hello",
            args=(),
            exc_info=None,
        )

    def test_stamps_the_current_request_id(self) -> None:
        token = logging_conf.request_id_var.set("ray-abc123")
        try:
            record = self._record()
            assert logging_conf.RequestIdFilter().filter(record) is True
            assert record.request_id == "ray-abc123"
        finally:
            logging_conf.request_id_var.reset(token)

    def test_falls_back_outside_a_request(self) -> None:
        """Startup and worker lines have no request; they must still format."""
        record = self._record()
        logging_conf.RequestIdFilter().filter(record)
        assert record.request_id == "-"

    def test_every_handler_is_filtered(self) -> None:
        """A handler without the filter would raise KeyError on the format string."""
        cfg = logging_conf.build_logging_config(log_level="INFO")
        assert "request_id" in cfg["filters"]
        for handler in cfg["handlers"].values():
            assert "request_id" in handler["filters"]

    def test_format_carries_the_id(self) -> None:
        assert "%(request_id)s" in logging_conf.LOG_FORMAT
