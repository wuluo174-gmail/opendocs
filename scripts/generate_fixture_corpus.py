"""S0 placeholder for fixture corpus generation."""

from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate fixture corpus (implemented in S11).")
    parser.add_argument(
        "--profile",
        default="acceptance",
        help="Fixture profile selector (implemented in S11)",
    )
    parser.add_argument(
        "--output",
        default=".tmp/corpus",
        help="Target directory for generated fixture corpus",
    )
    parser.add_argument(
        "--output-dir",
        dest="output",
        help=argparse.SUPPRESS,
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    print(
        "blocked: generate_fixture_corpus is reserved for S11. "
        f"requested profile={args.profile} output={args.output}"
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
