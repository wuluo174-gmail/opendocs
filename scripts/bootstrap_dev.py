"""Bootstrap local development dependencies for OpenDocs."""

from __future__ import annotations

import platform
import shutil
import subprocess
import sys
from pathlib import Path

_LOCKED_IMPORT_CHECKS = ("hnswlib",)


def _run(cmd: list[str]) -> int:
    completed = subprocess.run(cmd, check=False)
    return completed.returncode


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _requirements_lock_path() -> Path:
    return _project_root() / "requirements.lock"


def _project_venv_python_path() -> Path:
    if platform.system().lower() == "windows":
        return _project_root() / ".venv" / "Scripts" / "python.exe"
    return _project_root() / ".venv" / "bin" / "python"


def _detect_python_minor_version(python_path: Path) -> str | None:
    completed = subprocess.run(
        [
            str(python_path),
            "-c",
            "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')",
        ],
        capture_output=True,
        check=False,
        text=True,
    )
    if completed.returncode != 0:
        return None
    version = completed.stdout.strip()
    return version or None


def _validate_project_virtualenv() -> str | None:
    venv_python = _project_venv_python_path()
    if venv_python.is_symlink() and not venv_python.exists():
        return (
            "local .venv points to a missing interpreter. "
            "Remove .venv and recreate it with host-native Python 3.11."
        )
    if not venv_python.exists():
        return None

    version = _detect_python_minor_version(venv_python)
    if version is None:
        return (
            f"local .venv exists but its interpreter health check failed: {venv_python}. "
            "Remove .venv and recreate it with host-native Python 3.11."
        )
    if version != "3.11":
        return (
            f"local .venv uses Python {version}, expected 3.11. "
            "Remove .venv and recreate it with host-native Python 3.11."
        )
    return None


def _validate_lockfile_contract(lock_path: Path) -> str | None:
    """Return an error when the lock file contains remote/VCS requirements.

    S0 bootstrap must remain self-contained: third-party deps come from the
    lock file, while the local OpenDocs package is installed from the current
    workspace in a separate editable step below.
    """
    remote_markers = ("git+", "http://", "https://")
    for line_no, raw_line in enumerate(lock_path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if any(marker in line for marker in remote_markers):
            return (
                f"requirements lock contains a remote dependency at line {line_no}: {line}. "
                "Use only pinned third-party packages here; install the local workspace separately."
            )
    return None


def _is_python_311() -> bool:
    return sys.version_info.major == 3 and sys.version_info.minor == 11


def _delegate_to_python311_if_needed(argv: list[str]) -> int | None:
    if _is_python_311():
        return None

    if platform.system().lower() == "windows":
        py_launcher = shutil.which("py")
        if py_launcher:
            cmd = [py_launcher, "-3.11", str(Path(__file__).resolve()), *argv]
            print(
                "[bootstrap] locked baseline requires host-native Python 3.11; "
                "delegating to `py -3.11`."
            )
            return _run(cmd)

    print("[bootstrap] failed: locked baseline requires host-native Python 3.11.")
    print("[bootstrap] install host-native Python 3.11 and rerun this script.")
    return 1


def _install_locked_dependencies() -> int:
    project_root = _project_root()
    lock_path = _requirements_lock_path()
    if not lock_path.exists():
        print(f"[bootstrap] failed: requirements lock not found: {lock_path}")
        return 1
    validation_error = _validate_lockfile_contract(lock_path)
    if validation_error is not None:
        print(f"[bootstrap] failed: {validation_error}")
        return 1
    venv_error = _validate_project_virtualenv()
    if venv_error is not None:
        print(f"[bootstrap] failed: {venv_error}")
        return 1

    print(f"[bootstrap] python: {sys.version.split()[0]}")
    print(f"[bootstrap] installing locked dependencies from {lock_path.name}...")
    install_lock_cmd = [sys.executable, "-m", "pip", "install", "-r", str(lock_path)]
    if _run(install_lock_cmd) != 0:
        print(f"[bootstrap] failed: {' '.join(install_lock_cmd)}")
        return 1

    print("[bootstrap] installing editable package without dependency drift...")
    install_editable_cmd = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "-e",
        str(project_root),
        "--no-deps",
        "--no-build-isolation",
    ]
    if _run(install_editable_cmd) != 0:
        print(f"[bootstrap] failed: {' '.join(install_editable_cmd)}")
        return 1

    print("[bootstrap] verifying locked runtime modules...")
    for module_name in _LOCKED_IMPORT_CHECKS:
        import_check_cmd = [sys.executable, "-c", f"import {module_name}"]
        if _run(import_check_cmd) != 0:
            print(
                f"[bootstrap] failed: locked runtime module import check failed for '{module_name}'"
            )
            return 1

    print("[bootstrap] success")
    print("[bootstrap] next commands:")
    print(f"  {sys.executable} -m opendocs --help")
    print(f"  {sys.executable} -m pytest -q")
    return 0


def main(argv: list[str] | None = None) -> int:
    cli_args = argv or []
    delegated_exit = _delegate_to_python311_if_needed(cli_args)
    if delegated_exit is not None:
        return delegated_exit
    return _install_locked_dependencies()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
