"""Smoke tests for S0 baseline."""

from __future__ import annotations

import subprocess
import sys


def test_cli_help_smoke() -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "opendocs", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0
    assert "usage: opendocs" in completed.stdout
