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


def test_install_locked_dependencies_fails_when_project_venv_is_invalid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lock_path = tmp_path / "requirements.lock"
    lock_path.write_text("pytest==8.4.2\n", encoding="utf-8")
    commands: list[list[str]] = []
    monkeypatch.setattr(_MODULE, "_requirements_lock_path", lambda: lock_path)
    monkeypatch.setattr(
        _MODULE,
        "_validate_project_virtualenv",
        lambda: "local .venv points to a missing interpreter.",
    )
    monkeypatch.setattr(_MODULE, "_run", lambda cmd: commands.append(cmd) or 0)

    exit_code = _MODULE._install_locked_dependencies()

    assert exit_code == 1
    assert commands == []


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


def test_install_locked_dependencies_prints_explicit_next_commands(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    lock_path = tmp_path / "requirements.lock"
    lock_path.write_text("pytest==8.4.2\n", encoding="utf-8")
    project_root = tmp_path / "repo-root"
    project_root.mkdir(parents=True)

    monkeypatch.setattr(_MODULE, "_requirements_lock_path", lambda: lock_path)
    monkeypatch.setattr(_MODULE, "_project_root", lambda: project_root)
    monkeypatch.setattr(_MODULE, "_run", lambda cmd: 0)

    exit_code = _MODULE._install_locked_dependencies()
    stdout = capsys.readouterr().out

    assert exit_code == 0
    assert f"{sys.executable} -m opendocs --help" in stdout
    assert f"{sys.executable} -m pytest -q" in stdout


def test_install_locked_dependencies_fails_when_lock_contains_remote_dependency(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lock_path = tmp_path / "requirements.lock"
    lock_path.write_text(
        "pytest==8.4.2\n-e git+https://example.com/opendocs.git#egg=opendocs\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(_MODULE, "_requirements_lock_path", lambda: lock_path)
    commands: list[list[str]] = []
    monkeypatch.setattr(_MODULE, "_run", lambda cmd: commands.append(cmd) or 0)

    exit_code = _MODULE._install_locked_dependencies()

    assert exit_code == 1
    assert commands == []


def test_install_locked_dependencies_fails_when_hnswlib_import_check_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lock_path = tmp_path / "requirements.lock"
    lock_path.write_text("pytest==8.4.2\n", encoding="utf-8")
    project_root = tmp_path / "repo-root"
    project_root.mkdir(parents=True)

    commands: list[list[str]] = []

    def _fake_run(cmd: list[str]) -> int:
        commands.append(cmd)
        return 1 if cmd == [sys.executable, "-c", "import hnswlib"] else 0

    monkeypatch.setattr(_MODULE, "_requirements_lock_path", lambda: lock_path)
    monkeypatch.setattr(_MODULE, "_project_root", lambda: project_root)
    monkeypatch.setattr(_MODULE, "_run", _fake_run)

    exit_code = _MODULE._install_locked_dependencies()

    assert exit_code == 1
    assert commands[-1] == [sys.executable, "-c", "import hnswlib"]


def test_pyproject_requires_python_is_locked_to_311() -> None:
    pyproject_path = Path(__file__).resolve().parents[2] / "pyproject.toml"
    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    assert data["project"]["requires-python"] == ">=3.11,<3.12"


def test_pyproject_has_ruff_format_baseline_config() -> None:
    pyproject_path = Path(__file__).resolve().parents[2] / "pyproject.toml"
    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    assert data["tool"]["ruff"]["format"] == {
        "quote-style": "double",
        "indent-style": "space",
        "line-ending": "lf",
    }


def test_pyproject_core_dependencies_include_locked_stack_baseline() -> None:
    pyproject_path = Path(__file__).resolve().parents[2] / "pyproject.toml"
    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    runtime_dependencies = set(data["project"]["dependencies"])
    required_prefixes = {
        "PySide6>=",
        "watchdog>=",
        "hnswlib>=",
        "Jinja2>=",
        "keyring>=",
        "pyinstaller>=",
    }

    for prefix in required_prefixes:
        assert any(dep.startswith(prefix) for dep in runtime_dependencies), prefix


def test_pyproject_dev_extra_is_limited_to_dev_tooling() -> None:
    pyproject_path = Path(__file__).resolve().parents[2] / "pyproject.toml"
    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    dev_dependencies = set(data["project"]["optional-dependencies"]["dev"])
    required_prefixes = {
        "pytest>=",
        "pytest-qt>=",
        "pytest-cov>=",
        "ruff>=",
    }
    forbidden_prefixes = {
        "watchdog>=",
        "hnswlib>=",
        "Jinja2>=",
        "keyring>=",
        "pyinstaller>=",
        "PySide6>=",
    }

    for prefix in required_prefixes:
        assert any(dep.startswith(prefix) for dep in dev_dependencies), prefix
    for prefix in forbidden_prefixes:
        assert not any(dep.startswith(prefix) for dep in dev_dependencies), prefix


def test_requirements_lock_header_mentions_python311_baseline() -> None:
    lock_path = Path(__file__).resolve().parents[2] / "requirements.lock"
    header_line = lock_path.read_text(encoding="utf-8").splitlines()[2]
    assert header_line == "# Runtime: Python 3.11 baseline"


def test_requirements_lock_has_no_remote_or_vcs_lines() -> None:
    lock_path = Path(__file__).resolve().parents[2] / "requirements.lock"
    lines = [
        line.strip()
        for line in lock_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert all("git+" not in line for line in lines)
    assert all("http://" not in line for line in lines)
    assert all("https://" not in line for line in lines)


def test_requirements_lock_includes_build_backend_dependencies() -> None:
    lock_path = Path(__file__).resolve().parents[2] / "requirements.lock"
    lines = [
        line.strip()
        for line in lock_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]

    assert any(line.startswith("setuptools==") for line in lines)
    assert any(line.startswith("wheel==") for line in lines)


def test_python_version_file_locks_host_runtime_to_311() -> None:
    version_path = Path(__file__).resolve().parents[2] / ".python-version"
    assert version_path.read_text(encoding="utf-8").strip() == "3.11"
