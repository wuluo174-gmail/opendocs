"""S0 placeholder for fixture corpus generation."""

from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate fixture corpus (implemented in S11).")
    parser.add_argument(
        "--output-dir",
        default=".tmp/fixtures",
        help="Target directory for generated fixture corpus",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    print(
        "blocked: generate_fixture_corpus is reserved for S11. "
        f"requested output-dir={args.output_dir}"
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
