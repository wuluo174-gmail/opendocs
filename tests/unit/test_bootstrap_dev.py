"""Unit tests for scripts/bootstrap_dev.py behavior."""

from __future__ import annotations

import importlib.util
import sys
import tomllib
from pathlib import Path

import pytest

_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "bootstrap_dev.py"
_SPEC = importlib.util.spec_from_file_location("bootstrap_dev_script", _SCRIPT_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError(f"failed to load bootstrap script from {_SCRIPT_PATH}")
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)


def test_main_delegates_to_python311_on_windows_when_needed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[list[str]] = []
    monkeypatch.setattr(_MODULE, "_is_python_311", lambda: False)
    monkeypatch.setattr(_MODULE.platform, "system", lambda: "Windows")
    monkeypatch.setattr(_MODULE.shutil, "which", lambda _: "C:/Windows/py.exe")
    monkeypatch.setattr(_MODULE, "_run", lambda cmd: commands.append(cmd) or 0)

    exit_code = _MODULE.main([])

    assert exit_code == 0
    assert commands == [["C:/Windows/py.exe", "-3.11", str(_SCRIPT_PATH)]]


def test_main_fails_without_python311_runtime_or_launcher(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(_MODULE, "_is_python_311", lambda: False)
    monkeypatch.setattr(_MODULE.platform, "system", lambda: "Linux")
    monkeypatch.setattr(_MODULE.shutil, "which", lambda _: None)

    exit_code = _MODULE.main([])

    assert exit_code == 1


def test_install_locked_dependencies_uses_lock_then_editable_no_deps(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lock_path = tmp_path / "requirements.lock"
    lock_path.write_text("pytest==8.4.2\n", encoding="utf-8")
    project_root = tmp_path / "repo-root"
    project_root.mkdir(parents=True)

    commands: list[list[str]] = []
    monkeypatch.setattr(_MODULE, "_requirements_lock_path", lambda: lock_path)
    monkeypatch.setattr(_MODULE, "_project_root", lambda: project_root)
    monkeypatch.setattr(_MODULE, "_run", lambda cmd: commands.append(cmd) or 0)

    exit_code = _MODULE._install_locked_dependencies()

    assert exit_code == 0
    assert commands == [
        [sys.executable, "-m", "pip", "install", "-r", str(lock_path)],
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "-e",
            str(project_root),
            "--no-deps",
            "--no-build-isolation",
        ],
        [sys.executable, "-c", "import hnswlib"],
    ]


def test_install_locked_dependencies_fails_when_hnswlib_check_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lock_path = tmp_path / "requirements.lock"
    lock_path.write_text("pytest==8.4.2\n", encoding="utf-8")
    monkeypatch.setattr(_MODULE, "_requirements_lock_path", lambda: lock_path)

    call_count = {"n": 0}

    def _fake_run(_cmd: list[str]) -> int:
        call_count["n"] += 1
        if call_count["n"] < 3:
            return 0
        return 1

    monkeypatch.setattr(_MODULE, "_run", _fake_run)

    exit_code = _MODULE._install_locked_dependencies()

    assert exit_code == 1


def test_pyproject_requires_python_is_locked_to_311() -> None:
    pyproject_path = Path(__file__).resolve().parents[2] / "pyproject.toml"
    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    assert data["project"]["requires-python"] == ">=3.11,<3.12"


def test_requirements_lock_header_mentions_python311_baseline() -> None:
    lock_path = Path(__file__).resolve().parents[2] / "requirements.lock"
    header_line = lock_path.read_text(encoding="utf-8").splitlines()[2]
    assert header_line == "# Runtime: Python 3.11 baseline"
