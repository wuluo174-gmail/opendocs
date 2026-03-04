"""S0 placeholder for index rebuild script."""

from __future__ import annotations

import argparse
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Rebuild index (implemented in S3).")
    parser.add_argument(
        "--source",
        type=Path,
        default=None,
        help="Source directory to index",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    print(f"blocked: rebuild_index is reserved for S3. requested source={args.source}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
