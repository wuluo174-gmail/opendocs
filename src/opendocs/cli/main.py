"""CLI entrypoint for the OpenDocs baseline app."""

from __future__ import annotations

import argparse
from pathlib import Path

from opendocs import __version__
from opendocs.config import load_settings, resolve_app_root
from opendocs.exceptions import ConfigError
from opendocs.utils import init_logging


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="opendocs",
        description="OpenDocs baseline CLI.",
    )
    parser.add_argument("--version", action="store_true", help="Show OpenDocs version")
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Optional path to settings.toml",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.version:
        print(__version__)
        return 0

    try:
        settings = load_settings(args.config)
    except ConfigError as exc:
        print(f"config error: {exc}")
        return 2

    app_root = resolve_app_root(args.config)
    log_root = app_root / "logs"
    logger = init_logging(log_root)
    logger.info("OpenDocs CLI started")
    print("OpenDocs baseline started.")
    print(f"language={settings.app.language} local_only={settings.app.local_only}")
    return 0
