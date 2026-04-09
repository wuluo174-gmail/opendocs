"""Regression tests for the S3 stage report ownership contract."""

from __future__ import annotations

import re
from pathlib import Path

REPORT_PATH = Path("docs/test-plan/S3_stage_report.md")
EXPECTED_SNAPSHOT_RULE = "本节只记录当前仓库中仍然存在、且仍由 S3 主链路消费的 owner / 交付物快照。"
EXPECTED_FILE_IDENTITY_RULE = "`documents.file_identity` 改为“仅约束 active 行唯一”"
EXPECTED_BATCH_RESOLUTION_RULE = "增量索引现在以前一轮 active 文档集和本轮 scan 为输入统一决算"
EXPECTED_WATCHER_LIFECYCLE = (
    "fs_event -> queue -> SQLite source of truth -> HNSW derived update / mark_dirty -> audit"
)
EXPECTED_MIGRATION_REF = "src/opendocs/storage/schema/0012_documents_active_file_identity.sql"
REPO_PATH_RE = re.compile(r"`((?:src|tests|docs|scripts)/[^`]+)`")


class TestS3StageReportContract:
    @staticmethod
    def _section_text(report_text: str, heading: str, next_heading: str) -> str:
        start = report_text.index(heading)
        end = report_text.index(next_heading, start)
        return report_text[start:end]

    def test_report_tracks_current_s3_owner_and_state_machine_contract(self) -> None:
        repo_root = Path(__file__).resolve().parents[3]
        report_text = (repo_root / REPORT_PATH).read_text(encoding="utf-8")

        assert EXPECTED_SNAPSHOT_RULE in report_text
        assert EXPECTED_FILE_IDENTITY_RULE in report_text
        assert EXPECTED_BATCH_RESOLUTION_RULE in report_text
        assert EXPECTED_WATCHER_LIFECYCLE in report_text
        assert f"`{EXPECTED_MIGRATION_REF}`" in report_text

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
