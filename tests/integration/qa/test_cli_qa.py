"""CLI coverage for S5 QA, summary, and insight flows."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.engine import Engine

from opendocs.cli.main import main as cli_main


class TestCliQa:
    def test_cli_qa_answer_supports_fact_list_queries(
        self,
        indexed_qa_env: tuple[Engine, Path, Path],
        capsys,
    ) -> None:
        _, db_path, hnsw_path = indexed_qa_env

        exit_code = cli_main(
            [
                "qa",
                "answer",
                "Atlas 有哪些发布时间？",
                "--db",
                str(db_path),
                "--hnsw",
                str(hnsw_path),
            ]
        )

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "result_type=answered" in captured.out
        assert "Atlas 发布时间：2026-03-15" in captured.out
        assert "Atlas 发布时间：2026-04-01" in captured.out
        assert "Atlas 月报" not in captured.out

    def test_cli_qa_summary_supports_query_bundle(
        self,
        indexed_qa_env: tuple[Engine, Path, Path],
        capsys,
    ) -> None:
        _, db_path, hnsw_path = indexed_qa_env

        exit_code = cli_main(
            [
                "qa",
                "summary",
                "--query",
                "Atlas 关键决策",
                "--db",
                str(db_path),
                "--hnsw",
                str(hnsw_path),
            ]
        )

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "result_type=summary" in captured.out
        assert "决策" in captured.out
        assert "引用：" in captured.out

    def test_cli_qa_insights_requires_confirmation_before_export_write(
        self,
        indexed_qa_env: tuple[Engine, Path, Path],
        tmp_path: Path,
        capsys,
    ) -> None:
        _, db_path, hnsw_path = indexed_qa_env
        export_path = tmp_path / "atlas_insights.md"

        preview_exit = cli_main(
            [
                "qa",
                "insights",
                "--query",
                "Atlas 决策 风险 待办",
                "--export-path",
                str(export_path),
                "--export-title",
                "Atlas 洞察导出",
                "--db",
                str(db_path),
                "--hnsw",
                str(hnsw_path),
            ]
        )

        assert preview_exit == 1
        preview_output = capsys.readouterr().out
        assert "Markdown export preview:" in preview_output
        assert "export error: refusing to write without --confirmed" in preview_output
        assert not export_path.exists()

        save_exit = cli_main(
            [
                "qa",
                "insights",
                "--query",
                "Atlas 决策 风险 待办",
                "--export-path",
                str(export_path),
                "--export-title",
                "Atlas 洞察导出",
                "--confirmed",
                "--db",
                str(db_path),
                "--hnsw",
                str(hnsw_path),
            ]
        )

        assert save_exit == 0
        save_output = capsys.readouterr().out
        assert "export_status=saved" in save_output
        assert export_path.exists()
        assert "## 决策" in export_path.read_text(encoding="utf-8")
