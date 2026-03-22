"""Regression tests for deterministic TC-005 acceptance artifact capture."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from opendocs.retrieval.stage_acceptance_capture_cases import load_s4_acceptance_capture_cases
from opendocs.retrieval.stage_acceptance_corpora import load_s4_acceptance_corpora
from opendocs.retrieval.stage_acceptance_provenance import build_s4_tc005_input_provenance
from opendocs.retrieval.stage_filter_cases import load_s4_search_filter_cases
from opendocs.retrieval.stage_golden_queries import load_s4_hybrid_search_queries
from opendocs.ui.acceptance_capture import capture_s4_tc005_artifacts, planned_tc005_output_paths


class TestTc005ArtifactCapture:
    def test_capture_writes_manifest_query_log_and_screenshots(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "artifacts"
        manifest = capture_s4_tc005_artifacts(output_dir)

        manifest_path = output_dir / "manifest.json"
        query_log_path = output_dir / "query_results.json"
        assert manifest.case_id == "TC-005"
        assert "scripts/capture_s4_tc005_artifacts.py" in manifest.generator_command
        assert "--corpus-dir" not in manifest.generator_command
        assert manifest.corpus_dir == load_s4_acceptance_corpora().tc005.manifest_label
        assert manifest.input_provenance == build_s4_tc005_input_provenance()
        assert "query_lexicon_asset" in manifest.input_provenance
        assert "source_defaults_owner" in manifest.input_provenance
        assert manifest_path.exists()
        assert query_log_path.exists()
        assert len(manifest.artifacts) == 2

        payload = json.loads(query_log_path.read_text(encoding="utf-8"))
        expected_query_ids = {query.query_id for query in load_s4_hybrid_search_queries()}
        expected_filter_case_ids = {case.case_id for case in load_s4_search_filter_cases()}
        expected_capture_query_ids = {case.query_id for case in load_s4_acceptance_capture_cases().tc005}
        assert payload["case_id"] == "TC-005"
        assert payload["query_count"] == len(expected_query_ids)
        assert payload["filter_case_count"] == len(expected_filter_case_ids)
        assert {entry["query_id"] for entry in payload["logs"]} == expected_query_ids
        assert {entry["case_id"] for entry in payload["filter_logs"]} == expected_filter_case_ids
        assert all(entry["hit_in_top10"] for entry in payload["logs"])
        assert all(entry["hit_in_results"] for entry in payload["filter_logs"])

        artifact_paths = [Path(artifact.path) for artifact in manifest.artifacts]
        assert all(path.exists() for path in artifact_paths)
        planned_screenshot_paths = {
            path.name for path in planned_tc005_output_paths(output_dir) if path.suffix == ".png"
        }
        assert {path.name for path in artifact_paths} == planned_screenshot_paths
        assert {artifact.query_id for artifact in manifest.artifacts} == expected_capture_query_ids
        assert any("page=" in artifact.locator_label or "paragraph=" in artifact.locator_label for artifact in manifest.artifacts)
        assert all(artifact.preview_locator_label for artifact in manifest.artifacts)

    def test_capture_refuses_overwrite_without_force(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "artifacts"
        output_dir.mkdir(parents=True)
        planned_output = next(path for path in planned_tc005_output_paths(output_dir) if path.suffix == ".png")
        planned_output.write_bytes(b"already-exists")

        with pytest.raises(FileExistsError):
            capture_s4_tc005_artifacts(output_dir)
