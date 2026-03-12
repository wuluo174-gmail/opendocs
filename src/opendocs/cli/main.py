"""CLI entrypoint for the OpenDocs baseline app."""

from __future__ import annotations

import argparse
from pathlib import Path

from opendocs import __version__
from opendocs.config import load_settings, resolve_app_root
from opendocs.exceptions import ConfigError
from opendocs.utils import get_audit_logger, get_task_logger, init_logging


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

    # 初始化运行目录骨架（规范 §7.2）
    for _subdir in [
        Path("config"),
        Path("logs"),
        Path("data"),
        Path("index") / "hnsw",
        Path("index") / "cache",
        Path("rollback"),
        Path("output"),
        Path("temp"),
    ]:
        (app_root / _subdir).mkdir(parents=True, exist_ok=True)

    log_root = app_root / "logs"
    logger = init_logging(log_root)
    audit_logger = get_audit_logger()
    task_logger = get_task_logger()
    # CLI bootstrap creates the runtime log skeleton; later stages will append
    # structured audit/task events to these files via dedicated services.
    logger.info("OpenDocs CLI started")
    audit_logger.info("OpenDocs audit logger started")
    task_logger.info("OpenDocs task logger started")
    print("OpenDocs baseline started.")
    print(f"language={settings.app.language} local_only={settings.app.local_only}")
    return 0
