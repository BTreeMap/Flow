"""Tests for startup diagnostics logging."""

from __future__ import annotations

from app import config
from app.diagnostics import _redact_database_url, log_startup_report


class TestRedactDatabaseUrl:
    def test_postgres_url_drops_credentials(self) -> None:
        url = "postgresql+asyncpg://flow:secret@db.internal:5432/flowdb"
        redacted = _redact_database_url(url)
        assert "secret" not in redacted
        assert "flow:" not in redacted
        assert "db.internal" in redacted
        assert "flowdb" in redacted

    def test_sqlite_url_is_preserved_without_credentials(self) -> None:
        url = "sqlite+aiosqlite:///./data/flow-app.db"
        redacted = _redact_database_url(url)
        assert redacted.startswith("sqlite+aiosqlite")
        assert "flow-app.db" in redacted

    def test_unparseable_url_is_handled(self) -> None:
        assert isinstance(_redact_database_url("://::nonsense"), str)


class TestStartupReport:
    def test_reports_component_and_key_facts(self, caplog) -> None:
        with caplog.at_level("INFO", logger="app.diagnostics"):
            log_startup_report("api")

        messages = [rec.message for rec in caplog.records]
        joined = "\n".join(messages)
        assert "api startup diagnostics" in joined
        assert "database:" in joined
        assert any("prompt dir" in m for m in messages)
        assert any("config dir" in m for m in messages)
        # Never leak the raw key — only presence is reported.
        assert "LLM:" in joined

    def test_stub_mode_logs_warning(self, monkeypatch, caplog) -> None:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("H4CKATH0N_OPENAI_API_KEY", raising=False)
        config.clear_config_cache()
        try:
            with caplog.at_level("WARNING", logger="app.diagnostics"):
                log_startup_report("api")
            assert any(
                "stub mode" in rec.message and rec.levelname == "WARNING"
                for rec in caplog.records
            )
        finally:
            config.clear_config_cache()

    def test_prompt_probe_resolves_canary(self, caplog) -> None:
        with caplog.at_level("INFO", logger="app.diagnostics"):
            log_startup_report("worker")
        assert any("prompt probe" in rec.message for rec in caplog.records)

    def test_config_probe_resolves_canary(self, caplog) -> None:
        with caplog.at_level("INFO", logger="app.diagnostics"):
            log_startup_report("worker")
        assert any("config probe" in rec.message for rec in caplog.records)
