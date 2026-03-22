"""Capture deterministic screenshots for S4 TC-018 acceptance evidence."""

from __future__ import annotations

import argparse
from pathlib import Path

from opendocs.ui.acceptance_capture import (
    capture_s4_tc018_artifacts,
    default_tc018_output_dir,
    planned_tc018_output_paths,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Capture TC-018 acceptance screenshots for S4 evidence location."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=default_tc018_output_dir(),
        help="Directory used to store generated screenshots and manifest.json",
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
        help="Allow overwriting existing TC-018 artifacts in the output directory",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output_dir = args.output_dir.resolve()

    planned_outputs = planned_tc018_output_paths(output_dir)
    print("Planned outputs:")
    for path in planned_outputs:
        print(f"- {path}")

    try:
        manifest = capture_s4_tc018_artifacts(
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
    print(f"Manifest: {output_dir / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
