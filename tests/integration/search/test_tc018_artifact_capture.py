"""Regression tests for deterministic TC-018 acceptance artifact capture."""

from __future__ import annotations

from pathlib import Path

import pytest

from opendocs.acceptance.s4_capture_harness import (
    capture_s4_tc018_artifacts,
    planned_tc018_output_paths,
)
from opendocs.retrieval.stage_acceptance_capture_cases import load_s4_acceptance_capture_cases
from opendocs.retrieval.stage_acceptance_corpora import resolve_s4_tc018_corpus_dir
from opendocs.retrieval.stage_acceptance_provenance import build_s4_tc018_input_provenance


class TestTc018ArtifactCapture:
    def test_capture_writes_manifest_and_screenshots(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "artifacts"
        manifest = capture_s4_tc018_artifacts(output_dir)

        manifest_path = output_dir / "manifest.json"
        expected_cases = {case.slug: case for case in load_s4_acceptance_capture_cases().tc018}
        assert manifest.case_id == "TC-018"
        assert "scripts/capture_s4_tc018_artifacts.py" in manifest.generator_command
        assert "--corpus-dir" not in manifest.generator_command
        assert manifest.corpus_dir == str(resolve_s4_tc018_corpus_dir())
        assert manifest.input_provenance == build_s4_tc018_input_provenance()
        assert manifest_path.exists()
        assert len(manifest.artifacts) == 2

        artifact_paths = [Path(artifact.path) for artifact in manifest.artifacts]
        assert all(path.exists() for path in artifact_paths)
        planned_screenshot_paths = {
            path.name for path in planned_tc018_output_paths(output_dir) if path.suffix == ".png"
        }
        assert {path.name for path in artifact_paths} == planned_screenshot_paths
        for artifact in manifest.artifacts:
            expected_case = expected_cases[artifact.slug]
            assert Path(artifact.selected_document).name == expected_case.expected_file_name
            if expected_case.locator_kind == "page":
                assert "page=" in artifact.locator_label
            else:
                assert "paragraph=" in artifact.locator_label

    def test_capture_refuses_overwrite_without_force(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "artifacts"
        output_dir.mkdir(parents=True)
        planned_output = next(
            path for path in planned_tc018_output_paths(output_dir) if path.suffix == ".png"
        )
        planned_output.write_bytes(b"already-exists")

        with pytest.raises(FileExistsError):
            capture_s4_tc018_artifacts(output_dir)
