"""Unit tests for configuration loading behavior."""

from __future__ import annotations

from pathlib import Path

import pytest

from opendocs.config.settings import load_settings, resolve_app_root
from opendocs.exceptions import ConfigError


def test_load_settings_raises_on_missing_explicit_path() -> None:
    with pytest.raises(ConfigError, match="config path does not exist"):
        load_settings("does-not-exist.toml")


def test_load_settings_raises_on_missing_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    missing = Path("also-not-exist.toml")
    monkeypatch.setenv("OPENDOCS_CONFIG", str(missing))
    with pytest.raises(ConfigError, match="config path does not exist"):
        load_settings()


def test_resolve_app_root_for_canonical_layout(tmp_path: Path) -> None:
    config_path = tmp_path / "OpenDocs" / "config" / "settings.toml"
    assert resolve_app_root(config_path) == config_path.parent.parent.resolve()


def test_resolve_app_root_for_non_canonical_layout(tmp_path: Path) -> None:
    config_path = tmp_path / "review_custom" / "settings.toml"
    assert resolve_app_root(config_path) == config_path.parent.resolve()
