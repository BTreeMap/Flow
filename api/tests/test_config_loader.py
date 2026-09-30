"""Tests for the static JSON config dual-location resolver.

Mirrors tests/test_prompts.py::TestPromptResolution -- config resolution must
survive a stale/mounted ``config`` directory the same way prompt resolution
does, since both follow the identical override -> mountable -> baked-fallback
strategy (see app/config_loader.py).
"""

from __future__ import annotations

import pytest


class TestConfigResolution:
    def test_falls_back_when_primary_dir_missing_file(
        self, tmp_path: object, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app import config_loader

        empty_dir = tmp_path / "empty"  # type: ignore[operator]
        empty_dir.mkdir()
        monkeypatch.setenv("FLOW_CONFIG_DIR", str(empty_dir))

        path = config_loader.resolve_config_path("interventions.json")
        assert path.is_file()

    def test_override_dir_takes_precedence(
        self, tmp_path: object, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app import config_loader

        override_dir = tmp_path / "custom"  # type: ignore[operator]
        override_dir.mkdir()
        (override_dir / "interventions.json").write_text("{}", encoding="utf-8")
        monkeypatch.setenv("FLOW_CONFIG_DIR", str(override_dir))

        path = config_loader.resolve_config_path("interventions.json")
        assert path.parent == override_dir

    def test_missing_config_raises_file_not_found(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app import config_loader

        monkeypatch.delenv("FLOW_CONFIG_DIR", raising=False)
        with pytest.raises(FileNotFoundError):
            config_loader.resolve_config_path("does_not_exist_anywhere.json")

    def test_describe_resolution_reports_dirs(self) -> None:
        from app import config_loader

        dirs = config_loader.describe_resolution()
        assert len(dirs) >= 1
        for directory, exists in dirs:
            assert isinstance(directory, str)
            assert isinstance(exists, bool)
