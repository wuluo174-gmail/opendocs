"""Smoke tests for S0 baseline."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_exception_hierarchy_importable() -> None:
    from opendocs.exceptions import (
        BootstrapError,
        ConfigError,
        DeleteNotAllowedError,
        EvidenceInsufficientError,
        FileOpFailedError,
        IndexCorruptedError,
        MemoryConflictError,
        OpenDocsError,
        ParseFailedError,
        ParseUnsupportedError,
        PlanNotApprovedError,
        ProviderUnavailableError,
        RollbackPartialError,
        SourceNotFoundError,
        StorageError,
    )

    # 通用基类
    assert issubclass(ConfigError, OpenDocsError)
    assert issubclass(BootstrapError, OpenDocsError)
    assert issubclass(StorageError, OpenDocsError)

    # 规范 §11.3 业务错误码继承关系
    assert issubclass(SourceNotFoundError, OpenDocsError)
    assert issubclass(ParseUnsupportedError, OpenDocsError)
    assert issubclass(ParseFailedError, OpenDocsError)
    assert issubclass(IndexCorruptedError, StorageError)  # 存储层子类
    assert issubclass(EvidenceInsufficientError, OpenDocsError)
    assert issubclass(MemoryConflictError, OpenDocsError)
    assert issubclass(PlanNotApprovedError, OpenDocsError)
    assert issubclass(FileOpFailedError, OpenDocsError)
    assert issubclass(RollbackPartialError, OpenDocsError)
    assert issubclass(ProviderUnavailableError, OpenDocsError)
    assert issubclass(DeleteNotAllowedError, OpenDocsError)


def test_cli_help_smoke() -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "opendocs", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0
    assert "usage: opendocs" in completed.stdout


def test_cli_default_start_smoke(tmp_path: Path) -> None:
    app_root = tmp_path / "OpenDocs"
    config_dir = app_root / "config"
    config_dir.mkdir(parents=True)
    config_path = config_dir / "settings.toml"
    config_path.write_text("", encoding="utf-8")

    env = os.environ.copy()
    env["OPENDOCS_CONFIG"] = str(config_path.resolve())
    completed = subprocess.run(
        [sys.executable, "-m", "opendocs"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    assert completed.returncode == 0
    assert "OpenDocs baseline started." in completed.stdout
    log_file = app_root / "logs" / "app.log"
    assert log_file.exists()
    assert "OpenDocs CLI started" in log_file.read_text(encoding="utf-8")


def test_stage_scaffold_scripts_exist() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    scripts_dir = repo_root / "scripts"
    required = [
        "bootstrap_dev.py",
        "generate_fixture_corpus.py",
        "rebuild_index.py",
        "run_acceptance.py",
    ]
    for script_name in required:
        assert (scripts_dir / script_name).exists()


def test_generate_fixture_corpus_placeholder_cli_contract() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    script = repo_root / "scripts" / "generate_fixture_corpus.py"
    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--profile",
            "acceptance",
            "--output",
            ".tmp/corpus",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 2
    assert "requested profile=acceptance output=.tmp/corpus" in completed.stdout


def test_cli_uses_explicit_config_root_for_logs(tmp_path: Path) -> None:
    custom_root = tmp_path / "custom-root"
    config_dir = custom_root / "config"
    config_dir.mkdir(parents=True)
    config_path = config_dir / "settings.toml"
    config_path.write_text("", encoding="utf-8")

    env = os.environ.copy()
    env["APPDATA"] = str((tmp_path / "appdata").resolve())
    completed = subprocess.run(
        [sys.executable, "-m", "opendocs", "--config", str(config_path)],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert completed.returncode == 0
    log_file = custom_root / "logs" / "app.log"
    assert log_file.exists()
    assert "OpenDocs CLI started" in log_file.read_text(encoding="utf-8")


def test_cli_creates_runtime_directory_skeleton(tmp_path: Path) -> None:
    """CLI startup must create all §7.2 runtime directories under app_root."""
    app_root = tmp_path / "OpenDocs"
    config_dir = app_root / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "settings.toml").write_text("", encoding="utf-8")

    env = os.environ.copy()
    env["OPENDOCS_CONFIG"] = str((config_dir / "settings.toml").resolve())
    completed = subprocess.run(
        [sys.executable, "-m", "opendocs"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    assert completed.returncode == 0
    for expected in ["config", "logs", "data", "rollback", "output", "temp"]:
        assert (app_root / expected).is_dir(), f"missing runtime dir: {expected}/"
    assert (app_root / "index" / "hnsw").is_dir(), "missing: index/hnsw/"
    assert (app_root / "index" / "cache").is_dir(), "missing: index/cache/"


def test_cli_uses_non_canonical_explicit_config_root_for_logs(tmp_path: Path) -> None:
    custom_root = tmp_path / "review-custom"
    custom_root.mkdir(parents=True)
    config_path = custom_root / "settings.toml"
    config_path.write_text("", encoding="utf-8")

    env = os.environ.copy()
    env["APPDATA"] = str((tmp_path / "appdata").resolve())
    completed = subprocess.run(
        [sys.executable, "-m", "opendocs", "--config", str(config_path)],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert completed.returncode == 0
    log_file = custom_root / "logs" / "app.log"
    assert log_file.exists()
    assert "OpenDocs CLI started" in log_file.read_text(encoding="utf-8")
