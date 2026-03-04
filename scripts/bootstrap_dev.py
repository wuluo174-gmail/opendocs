"""Bootstrap local development dependencies for OpenDocs."""

from __future__ import annotations

import platform
import shutil
import subprocess
import sys
from pathlib import Path


def _run(cmd: list[str]) -> int:
    completed = subprocess.run(cmd, check=False)
    return completed.returncode


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _requirements_lock_path() -> Path:
    return _project_root() / "requirements.lock"


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
                "[bootstrap] locked baseline requires Python 3.11; "
                "delegating to `py -3.11`."
            )
            return _run(cmd)

    print("[bootstrap] failed: locked baseline requires Python 3.11 + hnswlib.")
    print("[bootstrap] install Python 3.11 and rerun this script.")
    return 1


def _install_locked_dependencies() -> int:
    project_root = _project_root()
    lock_path = _requirements_lock_path()
    if not lock_path.exists():
        print(f"[bootstrap] failed: requirements lock not found: {lock_path}")
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

    verify_hnswlib_cmd = [sys.executable, "-c", "import hnswlib"]
    if _run(verify_hnswlib_cmd) != 0:
        print("[bootstrap] failed: hnswlib import check failed.")
        return 1

    print("[bootstrap] success")
    print("[bootstrap] next commands:")
    print("  python -m opendocs --help")
    print("  pytest -q")
    return 0


def main(argv: list[str] | None = None) -> int:
    cli_args = argv or []
    delegated_exit = _delegate_to_python311_if_needed(cli_args)
    if delegated_exit is not None:
        return delegated_exit
    return _install_locked_dependencies()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
