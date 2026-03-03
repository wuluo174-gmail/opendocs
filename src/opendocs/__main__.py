"""Module entrypoint for `python -m opendocs`."""

from __future__ import annotations

from opendocs.cli.main import main


if __name__ == "__main__":
    raise SystemExit(main())
