"""Bootstrap local development dependencies for OpenDocs."""

from __future__ import annotations

import subprocess
import sys


def main() -> int:
    print(f"[bootstrap] python: {sys.version.split()[0]}")
    print("[bootstrap] installing editable package with dev dependencies...")
    cmd = [sys.executable, "-m", "pip", "install", "-e", ".[dev]"]
    completed = subprocess.run(cmd, check=False)
    if completed.returncode != 0:
        print(f"[bootstrap] failed: {' '.join(cmd)}")
        return completed.returncode

    print("[bootstrap] success")
    print("[bootstrap] next commands:")
    print("  python -m opendocs --help")
    print("  pytest -q")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
