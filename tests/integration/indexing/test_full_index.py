"""TC-001 & TC-002: Full index, source management, scan, failure isolation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine

from opendocs.app.index_service import IndexService
from opendocs.app.source_service import SourceService
from opendocs.domain.document_metadata import DocumentMetadata
from opendocs.indexing.scanner import ExcludeRules
from opendocs.storage.db import session_scope
from opendocs.storage.repositories import AuditRepository

# ---------------------------------------------------------------------------
# TC-001: Add root dir and scan
# ---------------------------------------------------------------------------


class TestTC001:
    """TC-001: source persisted, scan stats correct, audit logged."""

    def test_add_source_persists(
        self, source_service: SourceService, engine: Engine, corpus_copy: Path
    ) -> None:
        source = source_service.add_source(corpus_copy)
        assert source.source_root_id
        assert source.path == str(corpus_copy)

        # Reload from DB
        reloaded = source_service.get_source(source.source_root_id)
        assert reloaded is not None
        assert reloaded.path == str(corpus_copy)

    def test_add_source_idempotent(self, source_service: SourceService, corpus_copy: Path) -> None:
        s1 = source_service.add_source(corpus_copy)
        s2 = source_service.add_source(corpus_copy)
        assert s1.source_root_id == s2.source_root_id

    def test_add_source_persists_default_metadata(
        self, source_service: SourceService, corpus_copy: Path
    ) -> None:
        source = source_service.add_source(
            corpus_copy,
            default_metadata=DocumentMetadata(
                category="workspace",
                tags=["shared-source", "alpha"],
                sensitivity="internal",
            ),
        )

        reloaded = source_service.get_source(source.source_root_id)
        assert reloaded is not None
        assert reloaded.default_category == "workspace"
        assert reloaded.default_tags_json == ["shared-source", "alpha"]
        assert reloaded.default_sensitivity == "internal"

    def test_add_source_accepts_mapping_exclude_rules(
        self, source_service: SourceService, corpus_copy: Path
    ) -> None:
        source = source_service.add_source(
            corpus_copy,
            exclude_rules={
                "ignore_hidden": False,
                "exclude_globs": ["*.tmp"],
                "max_size_bytes": 123,
            },
        )

        assert source.exclude_rules_json["ignore_hidden"] is False
        assert source.exclude_rules_json["exclude_dirs"] == ["__pycache__", ".git"]
        assert source.exclude_rules_json["exclude_globs"] == ["*.tmp"]
        assert source.exclude_rules_json["max_size_bytes"] == 123

    def test_add_source_existing_path_updates_config(
        self, source_service: SourceService, corpus_copy: Path
    ) -> None:
        original = source_service.add_source(corpus_copy, label="first")

        updated = source_service.add_source(
            corpus_copy,
            label="second",
            exclude_rules=ExcludeRules(ignore_hidden=False, exclude_globs=["*.tmp"]),
            recursive=False,
        )

        assert updated.source_root_id == original.source_root_id
        assert updated.label == "second"
        assert updated.recursive is False
        assert updated.exclude_rules_json["ignore_hidden"] is False
        assert updated.exclude_rules_json["exclude_globs"] == ["*.tmp"]

    def test_update_source_updates_config(
        self, source_service: SourceService, corpus_copy: Path
    ) -> None:
        source = source_service.add_source(corpus_copy, label="before")

        updated = source_service.update_source(
            source.source_root_id,
            label=None,
            exclude_rules={
                "ignore_hidden": False,
                "max_size_bytes": 123,
            },
            recursive=False,
        )

        assert updated.label is None
        assert updated.recursive is False
        assert updated.exclude_rules_json["ignore_hidden"] is False
        assert updated.exclude_rules_json["exclude_dirs"] == ["__pycache__", ".git"]
        assert updated.exclude_rules_json["max_size_bytes"] == 123

    def test_update_source_reindexes_existing_documents(
        self,
        source_service: SourceService,
        index_service: IndexService,
        engine: Engine,
        corpus_copy: Path,
    ) -> None:
        source = source_service.add_source(
            corpus_copy,
            default_metadata=DocumentMetadata(
                category="workspace",
                tags=["shared-source"],
                sensitivity="internal",
            ),
        )
        index_service.full_index_source(source.source_root_id)
        target_path = str((corpus_copy / "report_001.txt").resolve())

        with session_scope(engine) as session:
            before_row = session.execute(
                text(
                    "SELECT category, tags_json, sensitivity "
                    "FROM documents WHERE path = :path"
                ),
                {"path": target_path},
            ).one()

        assert before_row[0] == "workspace"
        assert json.loads(before_row[1]) == ["shared-source"]
        assert before_row[2] == "internal"

        updated = source_service.update_source(
            source.source_root_id,
            default_metadata=DocumentMetadata(
                category="operations",
                tags=["ops-review"],
                sensitivity="sensitive",
            ),
        )

        assert updated.default_category == "operations"
        assert updated.default_tags_json == ["ops-review"]
        assert updated.default_sensitivity == "sensitive"

        with session_scope(engine) as session:
            after_row = session.execute(
                text(
                    "SELECT category, tags_json, sensitivity "
                    "FROM documents WHERE path = :path"
                ),
                {"path": target_path},
            ).one()
            incremental_audits = session.execute(
                text(
                    "SELECT COUNT(*) FROM audit_logs "
                    "WHERE operation = 'index_incremental' "
                    "AND json_extract(detail_json, '$.source_root_id') = :source_root_id"
                ),
                {"source_root_id": source.source_root_id},
            ).scalar()

        assert after_row[0] == "operations"
        assert json.loads(after_row[1]) == ["ops-review"]
        assert after_row[2] == "sensitive"
        assert incremental_audits >= 1

    def test_add_source_rejects_unreadable_root(
        self, source_service: SourceService, corpus_copy: Path, monkeypatch
    ) -> None:
        from opendocs.exceptions import SourceNotFoundError

        monkeypatch.setattr("opendocs.app.source_service.os.access", lambda _path, _mode: False)

        with pytest.raises(SourceNotFoundError, match="not readable"):
            source_service.add_source(corpus_copy)

    def test_scan_source_stats(self, source_service: SourceService, corpus_copy: Path) -> None:
        source = source_service.add_source(corpus_copy)
        scan_result, scan_run = source_service.scan_source(source.source_root_id)

        # Corpus: 3 txt + 3 md + 2 docx + 1 pdf = 9 supported
        # unsupported: legacy_format.doc = 1
        # excluded: empty_file.txt → excluded by parser (0-byte) but included in scan
        # corrupted.pdf → included (has bytes), will fail at parse time
        assert scan_result.included_count >= 9  # at least 9 parseable files
        assert scan_result.unsupported_count >= 1  # .doc

        # scan_run is independently readable
        assert scan_run.scan_run_id
        assert scan_run.status == "completed"
        assert scan_run.included_count == scan_result.included_count

    def test_scan_source_audit_logged(
        self, source_service: SourceService, engine: Engine, corpus_copy: Path, work_dir: Path
    ) -> None:
        source = source_service.add_source(corpus_copy)
        _, scan_run = source_service.scan_source(source.source_root_id)

        # DB audit exists
        with session_scope(engine) as session:
            audits = AuditRepository(session).query(
                target_type="index_run", trace_id=scan_run.trace_id
            )
            assert len(audits) >= 1
            assert audits[0].operation == "scan_source"

        # audit.jsonl exists and contains scan_source event
        audit_jsonl = work_dir / "logs" / "audit.jsonl"
        assert audit_jsonl.exists()
        lines = audit_jsonl.read_text().strip().split("\n")
        scan_events = [json.loads(line) for line in lines if "scan_source" in line]
        assert len(scan_events) >= 1

    def test_scan_source_failure_closes_scan_run_and_writes_failure_audit(
        self,
        source_service: SourceService,
        engine: Engine,
        corpus_copy: Path,
        work_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        source = source_service.add_source(corpus_copy)

        def raise_scan_failure(*args: object, **kwargs: object) -> object:
            raise RuntimeError("scanner exploded")

        monkeypatch.setattr(source_service._scanner, "scan", raise_scan_failure)

        with pytest.raises(RuntimeError, match="scanner exploded"):
            source_service.scan_source(source.source_root_id)

        with session_scope(engine) as session:
            scan_run = session.execute(
                text(
                    "SELECT scan_run_id, trace_id, status, finished_at, failed_count, "
                    "error_summary_json "
                    "FROM scan_runs WHERE source_root_id = :source_root_id "
                    "ORDER BY started_at DESC LIMIT 1"
                ),
                {"source_root_id": source.source_root_id},
            ).one()
            audits = AuditRepository(session).query(
                target_type="index_run",
                trace_id=scan_run[1],
            )

        assert scan_run[2] == "failed"
        assert scan_run[3] is not None
        assert scan_run[4] == 1
        error_summary = json.loads(scan_run[5])
        assert error_summary == [
            {"path": str(corpus_copy), "error": "RuntimeError: scanner exploded"}
        ]

        failure_audits = [audit for audit in audits if audit.operation == "scan_source"]
        assert len(failure_audits) == 1
        assert failure_audits[0].result == "failure"
        assert failure_audits[0].target_id == scan_run[0]
        assert failure_audits[0].detail_json["error_summary"] == error_summary

        audit_jsonl = work_dir / "logs" / "audit.jsonl"
        assert audit_jsonl.exists()
        scan_events = [
            json.loads(line)
            for line in audit_jsonl.read_text(encoding="utf-8").strip().splitlines()
            if '"operation": "scan_source"' in line
        ]
        assert any(
            event["result"] == "failure"
            and event["target_id"] == scan_run[0]
            and event["detail"]["error_summary"] == error_summary
            for event in scan_events
        )

    def test_full_index_links_scan_run_and_batch_audit(
        self,
        source_service: SourceService,
        index_service: IndexService,
        engine: Engine,
        corpus_copy: Path,
    ) -> None:
        source = source_service.add_source(corpus_copy)
        index_service.full_index_source(source.source_root_id)

        with session_scope(engine) as session:
            scan_run = session.execute(
                text(
                    "SELECT scan_run_id, trace_id, status "
                    "FROM scan_runs WHERE source_root_id = :source_root_id"
                ),
                {"source_root_id": source.source_root_id},
            ).one()
            audit_rows = session.execute(
                text(
                    "SELECT operation, target_id, trace_id "
                    "FROM audit_logs "
                    "WHERE target_type = 'index_run' "
                    "ORDER BY rowid"
                )
            ).fetchall()

        operations = {row[0] for row in audit_rows}
        assert "scan_source" in operations
        assert "index_full" in operations
        full_index_audit = next(row for row in audit_rows if row[0] == "index_full")
        assert scan_run[2] == "completed"
        assert full_index_audit[1] == scan_run[0]
        assert full_index_audit[2] == scan_run[1]

    def test_index_file_audit_queryable_by_file_path(
        self,
        source_service: SourceService,
        index_service: IndexService,
        engine: Engine,
        corpus_copy: Path,
    ) -> None:
        source = source_service.add_source(corpus_copy)
        index_service.full_index_source(source.source_root_id)
        expected_path = str((corpus_copy / "report_001.txt").resolve())

        with session_scope(engine) as session:
            audits = AuditRepository(session).query(
                target_type="document",
                file_path=expected_path,
            )
            index_audits = [a for a in audits if a.operation == "index_file"]

        assert len(index_audits) >= 1
        detail = index_audits[0].detail_json
        assert detail["file_path"] == expected_path

    def test_full_index_creates_documents_and_chunks(
        self,
        source_service: SourceService,
        index_service: IndexService,
        engine: Engine,
        corpus_copy: Path,
    ) -> None:
        source = source_service.add_source(corpus_copy)
        result = index_service.full_index_source(source.source_root_id)

        assert result.success_count >= 7  # most files should succeed
        assert result.total >= 9

        # Verify documents in DB
        with session_scope(engine) as session:
            doc_count = session.execute(text("SELECT COUNT(*) FROM documents")).scalar()
            chunk_count = session.execute(text("SELECT COUNT(*) FROM chunks")).scalar()
            assert doc_count >= 7
            assert chunk_count >= 7  # at least one chunk per doc

    def test_full_index_persists_directory_facts(
        self,
        source_service: SourceService,
        index_service: IndexService,
        engine: Engine,
        corpus_copy: Path,
    ) -> None:
        nested_file = corpus_copy / "projects" / "alpha" / "directory_fact.md"
        nested_file.parent.mkdir(parents=True, exist_ok=True)
        nested_file.write_text(
            "# Directory Fact\n\nPersist directory metadata.\n",
            encoding="utf-8",
        )

        source = source_service.add_source(corpus_copy)
        index_service.full_index_source(source.source_root_id)

        with session_scope(engine) as session:
            row = session.execute(
                text(
                    "SELECT directory_path, relative_directory_path "
                    "FROM documents WHERE path = :path"
                ),
                {"path": str(nested_file.resolve())},
            ).one()

        assert row == (
            str((corpus_copy / "projects" / "alpha").resolve()).replace("\\", "/"),
            "projects/alpha",
        )

    def test_fts5_searchable_after_index(
        self,
        source_service: SourceService,
        index_service: IndexService,
        engine: Engine,
        corpus_copy: Path,
    ) -> None:
        source = source_service.add_source(corpus_copy)
        index_service.full_index_source(source.source_root_id)

        with session_scope(engine) as session:
            rows = session.execute(
                text("SELECT chunk_id FROM chunk_fts WHERE chunk_fts MATCH 'UNIQUE_KW_001'")
            ).fetchall()
            assert len(rows) >= 1

    def test_full_index_hnsw_synced(
        self, source_service: SourceService, index_service: IndexService, corpus_copy: Path
    ) -> None:
        source = source_service.add_source(corpus_copy)
        result = index_service.full_index_source(source.source_root_id)
        assert result.hnsw_status == "synced"

    def test_exclude_rules_filtering(
        self, source_service: SourceService, corpus_copy: Path
    ) -> None:
        """S3-T05: exclude rules correctly filter hidden files and oversized files."""
        # Create files that should be excluded
        hidden = corpus_copy / ".hidden_file.txt"
        hidden.write_text("hidden content")
        large = corpus_copy / "oversized.txt"
        large.write_bytes(b"x" * 2000)

        rules = ExcludeRules(
            ignore_hidden=True,
            max_size_bytes=1000,
        )
        source = source_service.add_source(corpus_copy, exclude_rules=rules)
        scan_result, _ = source_service.scan_source(source.source_root_id)

        # Hidden and oversized files must be in excluded, not included
        included_rel = {f.relative_path for f in scan_result.included}
        assert ".hidden_file.txt" not in included_rel
        assert "oversized.txt" not in included_rel
        assert ".hidden_file.txt" in scan_result.excluded_paths
        assert "oversized.txt" in scan_result.excluded_paths


# ---------------------------------------------------------------------------
# TC-002: Unsupported and failed files don't crash batch
# ---------------------------------------------------------------------------


class TestTC002:
    """TC-002: failures recorded, good files indexed."""

    def test_failed_files_dont_crash_batch(
        self,
        source_service: SourceService,
        index_service: IndexService,
        engine: Engine,
        corpus_copy: Path,
    ) -> None:
        source = source_service.add_source(corpus_copy)
        result = index_service.full_index_source(source.source_root_id)

        # Batch completed without exception
        assert result.total >= 9
        assert result.success_count > 0
        # corrupted.pdf and empty_file.txt should fail
        assert result.failed_count >= 1

    def test_failed_documents_recorded_in_db(
        self,
        source_service: SourceService,
        index_service: IndexService,
        engine: Engine,
        corpus_copy: Path,
    ) -> None:
        source = source_service.add_source(corpus_copy)
        index_service.full_index_source(source.source_root_id)

        with session_scope(engine) as session:
            # Both success and failed documents exist
            success = session.execute(
                text("SELECT COUNT(*) FROM documents WHERE parse_status = 'success'")
            ).scalar()
            failed = session.execute(
                text("SELECT COUNT(*) FROM documents WHERE parse_status = 'failed'")
            ).scalar()
            assert success > 0
            assert failed >= 1

    def test_hash_failure_still_records_failed_document(
        self,
        source_service: SourceService,
        index_service: IndexService,
        engine: Engine,
        corpus_copy: Path,
        monkeypatch,
    ) -> None:
        from opendocs.indexing import index_builder as index_builder_module

        source = source_service.add_source(corpus_copy)
        target = (corpus_copy / "report_001.txt").resolve()
        real_compute_hash = index_builder_module._compute_hash

        def flaky_compute_hash(file_path: Path) -> str:
            if Path(file_path).resolve() == target:
                raise OSError("simulated hash failure")
            return real_compute_hash(file_path)

        monkeypatch.setattr(index_builder_module, "_compute_hash", flaky_compute_hash)

        result = index_service.full_index_source(source.source_root_id)
        failure_results = [
            entry for entry in result.results if Path(entry.path).resolve() == target
        ]
        assert len(failure_results) == 1
        assert failure_results[0].status == "failed"

        with session_scope(engine) as session:
            document_row = session.execute(
                text("SELECT parse_status, hash_sha256 FROM documents WHERE path = :path"),
                {"path": str(target)},
            ).fetchone()
            assert document_row is not None
            assert document_row[0] == "failed"
            assert document_row[1] is None

            chunk_count = session.execute(
                text(
                    "SELECT COUNT(*) FROM chunks c "
                    "JOIN documents d ON c.doc_id = d.doc_id "
                    "WHERE d.path = :path"
                ),
                {"path": str(target)},
            ).scalar()
            assert chunk_count == 0

            hash_failure_audits = session.execute(
                text(
                    "SELECT COUNT(*) FROM audit_logs "
                    "WHERE operation = 'index_file' "
                    "AND result = 'failure' "
                    "AND json_extract(detail_json, '$.error_stage') = 'hash'"
                )
            ).scalar()
            assert hash_failure_audits >= 1

    def test_unsupported_in_excluded_list(
        self, source_service: SourceService, corpus_copy: Path
    ) -> None:
        """FR-001: unsupported files enter the excluded list."""
        source = source_service.add_source(corpus_copy)
        scan_result, _ = source_service.scan_source(source.source_root_id)

        # .doc file should be in both unsupported_paths AND excluded_paths
        assert scan_result.unsupported_count >= 1
        doc_in_excluded = any("legacy_format.doc" in p for p in scan_result.excluded_paths)
        assert doc_in_excluded, (
            f"legacy_format.doc not found in excluded_paths: {scan_result.excluded_paths}"
        )
