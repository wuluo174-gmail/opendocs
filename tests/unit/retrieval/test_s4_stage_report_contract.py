"""Regression tests for the S4 stage report ownership contract."""

from __future__ import annotations

import re
from importlib.util import find_spec
from pathlib import Path

from opendocs.acceptance.s4_capture_harness import (
    default_tc005_output_dir,
    default_tc018_output_dir,
)

REPORT_PATH = Path("docs/test-plan/S4_stage_report.md")
LEGACY_CAPTURE_REF = "src/opendocs/ui/acceptance_capture.py"
EXPECTED_LIFECYCLE = (
    "stage assets -> acceptance runtime (SQLite/HNSW) -> SearchService -> "
    "SearchWindow -> artifacts/manifest"
)
EXPECTED_UI_BOUNDARY = "`opendocs.ui` 只保留可复用部件"
EXPECTED_SNAPSHOT_RULE = "本节只记录当前仓库中仍然存在、且仍由 S4 主链路消费的 owner / 交付物快照。"
REPO_PATH_RE = re.compile(r"`((?:src|tests|docs|scripts)/[^`]+)`")


class TestS4StageReportContract:
    @staticmethod
    def _section_text(report_text: str, heading: str, next_heading: str) -> str:
        start = report_text.index(heading)
        end = report_text.index(next_heading, start)
        return report_text[start:end]

    def test_report_tracks_current_acceptance_harness_owner(self) -> None:
        repo_root = Path(__file__).resolve().parents[3]
        report_text = (repo_root / REPORT_PATH).read_text(encoding="utf-8")
        harness_spec = find_spec("opendocs.acceptance.s4_capture_harness")

        assert harness_spec is not None
        assert harness_spec.origin is not None

        harness_ref = Path(harness_spec.origin).resolve().relative_to(repo_root).as_posix()

        assert f"`{harness_ref}`" in report_text
        assert LEGACY_CAPTURE_REF not in report_text
        assert EXPECTED_LIFECYCLE in report_text
        assert EXPECTED_UI_BOUNDARY in report_text
        assert EXPECTED_SNAPSHOT_RULE in report_text

    def test_default_capture_output_dirs_are_repo_scoped(self) -> None:
        repo_root = Path(__file__).resolve().parents[3]
        assert default_tc005_output_dir() == (
            repo_root / "docs" / "acceptance" / "artifacts" / "s4" / "tc005"
        )
        assert default_tc018_output_dir() == (
            repo_root / "docs" / "acceptance" / "artifacts" / "s4" / "tc018"
        )

    def test_section_one_repo_paths_exist(self) -> None:
        repo_root = Path(__file__).resolve().parents[3]
        report_text = (repo_root / REPORT_PATH).read_text(encoding="utf-8")
        section_text = self._section_text(
            report_text,
            "## 1. 新增/修改文件列表",
            "## 2. 关键实现说明",
        )
        report_paths = {
            ref.split("#", 1)[0].rstrip("/") for ref in REPO_PATH_RE.findall(section_text)
        }

        missing_paths = sorted(path for path in report_paths if not (repo_root / path).exists())

        assert LEGACY_CAPTURE_REF not in report_paths
        assert not missing_paths
