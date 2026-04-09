"""Regression tests for the S2 stage report ownership contract."""

from __future__ import annotations

import re
from pathlib import Path

REPORT_PATH = Path("docs/test-plan/S2_stage_report.md")
EXPECTED_SNAPSHOT_RULE = "本节只记录当前仓库中仍然存在、且仍由 S2 主链路消费的 owner / 交付物快照。"
EXPECTED_LIFECYCLE = (
    "file bytes / structure -> parser._parse_raw -> BaseParser.parse(finalize) -> "
    "ParsedDocument -> Chunker -> index consumers"
)
EXPECTED_OWNER_RULE = "BaseParser.parse()` 是 S2 最终解析契约的唯一 owner"
REPO_PATH_RE = re.compile(r"`((?:src|tests|docs|scripts)/[^`]+)`")


class TestS2StageReportContract:
    @staticmethod
    def _section_text(report_text: str, heading: str, next_heading: str) -> str:
        start = report_text.index(heading)
        end = report_text.index(next_heading, start)
        return report_text[start:end]

    def test_report_tracks_current_s2_owner_and_lifecycle_contract(self) -> None:
        repo_root = Path(__file__).resolve().parents[3]
        report_text = (repo_root / REPORT_PATH).read_text(encoding="utf-8")

        assert EXPECTED_SNAPSHOT_RULE in report_text
        assert EXPECTED_LIFECYCLE in report_text
        assert EXPECTED_OWNER_RULE in report_text

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

        assert not missing_paths
