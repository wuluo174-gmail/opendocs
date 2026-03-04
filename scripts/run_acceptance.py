"""S0 placeholder for acceptance runner."""

from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run acceptance suite (implemented in S11).")
    parser.add_argument(
        "--suite",
        default="full",
        choices=["smoke", "full"],
        help="Acceptance suite selector",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    print(f"blocked: run_acceptance is reserved for S11. requested suite={args.suite}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
