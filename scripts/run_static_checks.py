"""Run the S0 static check baseline from a single authority script."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _run(cmd: list[str], *, cwd: Path) -> int:
    print(f"[static-check] running: {' '.join(cmd)}")
    completed = subprocess.run(cmd, cwd=cwd, check=False)
    return completed.returncode


def main() -> int:
    project_root = _project_root()
    commands = [
        [sys.executable, "-m", "ruff", "check", "."],
        [sys.executable, "-m", "ruff", "format", "--check", "."],
    ]

    for command in commands:
        if _run(command, cwd=project_root) != 0:
            return 1

    print("[static-check] success")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
