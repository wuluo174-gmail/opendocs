"""CLI search subcommand smoke test + open_document behavior verification."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from sqlalchemy.engine import Engine

from opendocs.app.search_service import SearchService
from opendocs.cli.main import main as cli_main
from opendocs.exceptions import SchemaCompatibilityError
from opendocs.retrieval.evidence_locator import EvidenceLocator


class TestCliSearchSmoke:
    """Verify the CLI search subcommand runs and produces output."""

    def test_cli_source_commands_drive_metadata_lifecycle(
        self,
        search_corpus: Path,
        tmp_path: Path,
        capsys,
    ) -> None:
        db_path = tmp_path / "source_cli.db"
        hnsw_path = tmp_path / "hnsw" / "vectors.bin"

        exit_code = cli_main(
            [
                "source",
                "add",
                str(search_corpus),
                "--db",
                str(db_path),
                "--hnsw",
                str(hnsw_path),
                "--category",
                "Workspace",
                "--tag",
                "Shared-Source",
                "--sensitivity",
                "internal",
                "--exclude-dir",
                "tmp-cache",
                "--exclude-glob",
                "*.tmp",
                "--max-size-bytes",
                "2048",
            ]
        )
        assert exit_code == 0
        add_output = capsys.readouterr().out
        assert "exclude_ignore_hidden=True" in add_output
        assert "exclude_dirs=__pycache__,.git,tmp-cache" in add_output
        assert "exclude_globs=*.tmp" in add_output
        assert "exclude_max_size_bytes=2048" in add_output
        source_root_id = next(
            line.split("=", 1)[1]
            for line in add_output.splitlines()
            if line.startswith("source_root_id=")
        )

        exit_code = cli_main(
            [
                "source",
                "update",
                source_root_id,
                "--db",
                str(db_path),
                "--hnsw",
                str(hnsw_path),
                "--category",
                "Operations",
                "--tag",
                "Ops-Review",
                "--sensitivity",
                "sensitive",
                "--no-ignore-hidden",
                "--exclude-dir",
                "archive",
                "--clear-exclude-globs",
                "--exclude-glob",
                "*.bak",
                "--clear-max-size-bytes",
            ]
        )
        assert exit_code == 0
        update_output = capsys.readouterr().out
        assert "source_status=updated" in update_output
        assert "exclude_ignore_hidden=False" in update_output
        assert "exclude_dirs=__pycache__,.git,tmp-cache,archive" in update_output
        assert "exclude_globs=*.bak" in update_output
        assert "exclude_max_size_bytes=" in update_output
        assert "default_category=operations" in update_output
        assert "default_tags=ops-review" in update_output
        assert "default_sensitivity=sensitive" in update_output

        exit_code = cli_main(
            [
                "search",
                "authentication",
                "--db",
                str(db_path),
                "--hnsw",
                str(hnsw_path),
                "--category",
                "operations",
                "--tag",
                "ops-review",
                "--sensitivity",
                "sensitive",
            ]
        )
        assert exit_code == 0
        search_output = capsys.readouterr().out
        assert "en_weekly_report.txt" in search_output

        exit_code = cli_main(
            [
                "source",
                "list",
                "--db",
                str(db_path),
                "--hnsw",
                str(hnsw_path),
            ]
        )
        assert exit_code == 0
        list_output = capsys.readouterr().out
        assert f"source_root_id={source_root_id}" in list_output
        assert "exclude_ignore_hidden=False" in list_output
        assert "exclude_dirs=__pycache__,.git,tmp-cache,archive" in list_output
        assert "exclude_globs=*.bak" in list_output
        assert "default_category=operations" in list_output

    def test_cli_status_reports_runtime_index_state(
        self,
        indexed_search_env: tuple[Engine, Path, Path],
        capsys,
    ) -> None:
        _, db_path, hnsw_path = indexed_search_env
        exit_code = cli_main(
            [
                "status",
                "--db",
                str(db_path),
                "--hnsw",
                str(hnsw_path),
            ]
        )
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "active_sources=" in captured.out
        assert "documents=" in captured.out
        assert "watcher_running=False" in captured.out

    def test_cli_search_returns_results(
        self, indexed_search_env: tuple[Engine, Path, Path], capsys
    ) -> None:
        engine, db_path, hnsw_path = indexed_search_env
        exit_code = cli_main(
            [
                "search",
                "项目进度",
                "--db",
                str(db_path),
                "--hnsw",
                str(hnsw_path),
            ]
        )
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "项目" in captured.out or "Score" in captured.out

    def test_cli_search_supports_metadata_filters(
        self,
        indexed_search_env: tuple[Engine, Path, Path],
        capsys,
    ) -> None:
        _, db_path, hnsw_path = indexed_search_env
        exit_code = cli_main(
            [
                "search",
                "项目",
                "--db",
                str(db_path),
                "--hnsw",
                str(hnsw_path),
                "--category",
                "Project",
                "--tag",
                "Roadmap,Shared-Source",
                "--sensitivity",
                "Sensitive",
                "--time-from",
                "2026-03-01T00:00:00",
                "--time-to",
                "2026-03-20T23:59:59",
            ]
        )
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "zh_project_plan.md" in captured.out

    def test_cli_search_audit_uses_query_digest_not_raw_query(
        self,
        indexed_search_env: tuple[Engine, Path, Path],
        tmp_path: Path,
        capsys,
        monkeypatch,
    ) -> None:
        _, db_path, hnsw_path = indexed_search_env
        config_dir = tmp_path / "runtime" / "config"
        config_dir.mkdir(parents=True)
        config_path = config_dir / "settings.toml"
        config_path.write_text("", encoding="utf-8")
        monkeypatch.setenv("OPENDOCS_CONFIG", str(config_path))

        exit_code = cli_main(
            [
                "search",
                "password=abc123 token=mytoken",
                "--db",
                str(db_path),
                "--hnsw",
                str(hnsw_path),
            ]
        )
        assert exit_code == 0
        capsys.readouterr()

        audit_log = config_dir.parent / "logs" / "audit.jsonl"
        content = audit_log.read_text(encoding="utf-8")
        assert "password=abc123" not in content
        assert "mytoken" not in content
        assert "query_sha256" in content

    def test_cli_search_empty_query(
        self, indexed_search_env: tuple[Engine, Path, Path], capsys
    ) -> None:
        engine, db_path, hnsw_path = indexed_search_env
        exit_code = cli_main(
            [
                "search",
                "   ",
                "--db",
                str(db_path),
                "--hnsw",
                str(hnsw_path),
            ]
        )
        assert exit_code == 1

    def test_cli_search_no_results(
        self, indexed_search_env: tuple[Engine, Path, Path], capsys
    ) -> None:
        engine, db_path, hnsw_path = indexed_search_env
        exit_code = cli_main(
            [
                "search",
                "qxzjkw vbnmrt ypflg",
                "--db",
                str(db_path),
                "--hnsw",
                str(hnsw_path),
            ]
        )
        capsys.readouterr()
        # Either "No results found" or very few low-score results
        assert exit_code == 0

    def test_cli_search_open_result_branch(
        self, indexed_search_env: tuple[Engine, Path, Path], capsys
    ) -> None:
        _, db_path, hnsw_path = indexed_search_env

        with patch(
            "opendocs.app.search_service.EvidenceLocator.open_file",
            return_value=True,
        ) as open_mock:
            exit_code = cli_main(
                [
                    "search",
                    "项目进度",
                    "--db",
                    str(db_path),
                    "--hnsw",
                    str(hnsw_path),
                    "--open",
                    "1",
                ]
            )

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "Opened:" in captured.out
        _, kwargs = open_mock.call_args
        assert "char_range" in kwargs
        assert kwargs["char_range"]

    def test_cli_search_reports_schema_incompatibility(
        self,
        tmp_path: Path,
        monkeypatch,
        capsys,
    ) -> None:
        db_path = tmp_path / "stale.db"
        db_path.write_text("stale", encoding="utf-8")
        hnsw_path = tmp_path / "vectors.bin"

        def _raise_schema_error(_db_path: Path) -> list[str]:
            raise SchemaCompatibilityError(
                "database schema is incompatible. Rebuild the local database."
            )

        monkeypatch.setattr("opendocs.storage.db.init_db", _raise_schema_error)

        exit_code = cli_main(
            [
                "search",
                "项目进度",
                "--db",
                str(db_path),
                "--hnsw",
                str(hnsw_path),
            ]
        )

        assert exit_code == 2
        captured = capsys.readouterr()
        assert "schema error:" in captured.out
        assert "Rebuild the local database" in captured.out


class TestOpenDocument:
    """Verify open_document and open_file behavior."""

    def test_open_document_existing_file(self, search_service: SearchService) -> None:
        resp = search_service.search("项目进度")
        assert len(resp.results) > 0
        # Mock the subprocess call to avoid actually opening files
        with patch("opendocs.retrieval.evidence_locator.subprocess.Popen"):
            result = search_service.open_evidence(resp.results[0].doc_id, resp.results[0].chunk_id)
        assert result is True

    def test_open_document_nonexistent_file(self, search_service: SearchService) -> None:
        result = search_service.open_document(
            "/nonexistent/path/file.txt",
            paragraph_range="1-2",
            char_range="0-10",
        )
        assert result is False

    def test_open_file_static_method(self, tmp_path: Path) -> None:
        test_file = tmp_path / "test.txt"
        test_file.write_text("test")
        with patch("opendocs.retrieval.evidence_locator.subprocess.Popen"):
            result = EvidenceLocator.open_file(
                str(test_file),
                paragraph_range="2-3",
                char_range="5-9",
            )
        assert result is True

    def test_open_file_non_pdf_threads_locator_hints(self, tmp_path: Path) -> None:
        doc_file = tmp_path / "note.md"
        doc_file.write_text("note")
        with patch("opendocs.retrieval.evidence_locator.subprocess.Popen") as open_mock:
            result = EvidenceLocator.open_file(
                str(doc_file),
                paragraph_range="2-3",
                char_range="5-9",
            )
        assert result is True
        command = open_mock.call_args.args[0]
        assert "#paragraph=2-3" in command[-1]
        assert "char=5-9" in command[-1]

    def test_open_file_pdf_threads_page_hint(self, tmp_path: Path) -> None:
        pdf_file = tmp_path / "paper.pdf"
        pdf_file.write_text("fake pdf")
        with patch("opendocs.retrieval.evidence_locator.subprocess.Popen") as open_mock:
            result = EvidenceLocator.open_file(str(pdf_file), page_no=3, char_range="10-20")
        assert result is True
        command = open_mock.call_args.args[0]
        assert "#page=3" in command[-1]
