"""Capture deterministic artifacts for S4 TC-005 acceptance evidence."""

from __future__ import annotations

import argparse
from pathlib import Path

from opendocs.ui.acceptance_capture import (
    capture_s4_tc005_artifacts,
    default_tc005_output_dir,
    planned_tc005_output_paths,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Capture TC-005 acceptance artifacts for S4 hybrid search evidence."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=default_tc005_output_dir(),
        help="Directory used to store generated screenshots, query_results.json and manifest.json",
    )
    parser.add_argument(
        "--corpus-dir",
        type=Path,
        default=None,
        help="Optional external corpus directory; defaults to the stage-owned S4 acceptance corpus",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Allow overwriting existing TC-005 artifacts in the output directory",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output_dir = args.output_dir.resolve()

    planned_outputs = planned_tc005_output_paths(output_dir)
    print("Planned outputs:")
    for path in planned_outputs:
        print(f"- {path}")

    try:
        manifest = capture_s4_tc005_artifacts(
            output_dir,
            corpus_dir=args.corpus_dir,
            force=args.force,
        )
    except FileExistsError as exc:
        print(f"error: {exc}")
        return 2
    except FileNotFoundError as exc:
        print(f"error: {exc}")
        return 2

    print("Captured artifacts:")
    for artifact in manifest.artifacts:
        print(f"- {artifact.slug}: {artifact.path}")
    print(f"Query log: {manifest.query_log_path}")
    print(f"Manifest: {output_dir / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
