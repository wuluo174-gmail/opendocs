"""TC-003 & TC-004: Incremental indexing after file add/delete/modify."""

from __future__ import annotations

import uuid
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Engine

from opendocs.app.index_service import IndexService
from opendocs.app.source_service import SourceService
from opendocs.indexing.scanner import ScanResult, _derive_file_identity
from opendocs.storage.db import session_scope
from opendocs.storage.repositories import AuditRepository
from opendocs.utils.path_facts import build_display_path, derive_directory_facts

# ---------------------------------------------------------------------------
# TC-003: New file after indexing appears in search
# ---------------------------------------------------------------------------


class TestTC003:
    """TC-003: new file indexed incrementally, searchable via FTS."""

    def test_new_file_indexed_incrementally(
        self,
        source_service: SourceService,
        index_service: IndexService,
        engine: Engine,
        corpus_copy: Path,
    ) -> None:
        source = source_service.add_source(corpus_copy)
        index_service.full_index_source(source.source_root_id)

        # Add a new file with a unique keyword
        new_file = corpus_copy / "incremental_test.txt"
        new_file.write_text("This document contains UNIQUE_KW_INCR_999 for testing.")

        result = index_service.update_index_for_changes(source.source_root_id)
        # The new file should be indexed (not skipped)
        new_results = [r for r in result.results if "incremental_test" in r.path]
        assert len(new_results) == 1
        assert new_results[0].status == "success"

    def test_new_file_searchable_via_fts(
        self,
        source_service: SourceService,
        index_service: IndexService,
        engine: Engine,
        corpus_copy: Path,
    ) -> None:
        source = source_service.add_source(corpus_copy)
        index_service.full_index_source(source.source_root_id)

        new_file = corpus_copy / "fts_test_new.md"
        new_file.write_text("# FTS Test\n\nUNIQUE_KW_FTS_NEW_DOC content here.")

        index_service.update_index_for_changes(source.source_root_id)

        with session_scope(engine) as session:
            rows = session.execute(
                text("SELECT chunk_id FROM chunk_fts WHERE chunk_fts MATCH 'UNIQUE_KW_FTS_NEW_DOC'")
            ).fetchall()
            assert len(rows) >= 1

    def test_indexed_at_after_add_time(
        self,
        source_service: SourceService,
        index_service: IndexService,
        engine: Engine,
        corpus_copy: Path,
    ) -> None:
        source = source_service.add_source(corpus_copy)
        index_service.full_index_source(source.source_root_id)

        new_file = corpus_copy / "timestamp_test.txt"
        new_file.write_text("Timestamp test UNIQUE_KW_TS_001.")

        index_service.update_index_for_changes(source.source_root_id)

        with session_scope(engine) as session:
            row = session.execute(
                text("SELECT indexed_at FROM documents WHERE path LIKE '%timestamp_test%'")
            ).fetchone()
            assert row is not None
            # indexed_at should exist (not None)
            assert row[0] is not None

    def test_incremental_hnsw_synced(
        self, source_service: SourceService, index_service: IndexService, corpus_copy: Path
    ) -> None:
        source = source_service.add_source(corpus_copy)
        index_service.full_index_source(source.source_root_id)

        new_file = corpus_copy / "hnsw_sync_test.txt"
        new_file.write_text("HNSW sync test content.")

        result = index_service.update_index_for_changes(source.source_root_id)
        assert result.dense_reconcile_status == "synced"

    def test_modified_file_updated_incrementally(
        self,
        source_service: SourceService,
        index_service: IndexService,
        engine: Engine,
        corpus_copy: Path,
    ) -> None:
        """FR-002: modified file gets re-chunked on incremental update."""
        source = source_service.add_source(corpus_copy)
        index_service.full_index_source(source.source_root_id)

        # Confirm original keyword exists
        with session_scope(engine) as session:
            rows = session.execute(
                text("SELECT chunk_id FROM chunk_fts WHERE chunk_fts MATCH 'UNIQUE_KW_001'")
            ).fetchall()
            assert len(rows) >= 1

        # Modify report_001.txt with new content
        target = corpus_copy / "report_001.txt"
        target.write_text("MODIFIED CONTENT UNIQUE_KW_INCR_MOD_777")

        result = index_service.update_index_for_changes(source.source_root_id)
        mod_results = [r for r in result.results if "report_001" in r.path]
        assert len(mod_results) == 1
        assert mod_results[0].status == "success"

        # New keyword searchable, old keyword gone
        with session_scope(engine) as session:
            new_rows = session.execute(
                text(
                    "SELECT chunk_id FROM chunk_fts WHERE chunk_fts MATCH 'UNIQUE_KW_INCR_MOD_777'"
                )
            ).fetchall()
            assert len(new_rows) >= 1

            old_rows = session.execute(
                text("SELECT chunk_id FROM chunk_fts WHERE chunk_fts MATCH 'UNIQUE_KW_001'")
            ).fetchall()
            assert len(old_rows) == 0

    def test_parse_failure_replaces_old_index_content(
        self,
        source_service: SourceService,
        index_service: IndexService,
        engine: Engine,
        corpus_copy: Path,
    ) -> None:
        """Previously indexed content must be removed if a later reparse fails."""
        source = source_service.add_source(corpus_copy)
        index_service.full_index_source(source.source_root_id)

        target = corpus_copy / "report_001.txt"
        target.write_text("", encoding="utf-8")

        result = index_service.update_index_for_changes(source.source_root_id)
        failure_results = [r for r in result.results if "report_001" in r.path]
        assert len(failure_results) == 1
        assert failure_results[0].status == "failed"

        with session_scope(engine) as session:
            stale_rows = session.execute(
                text("SELECT chunk_id FROM chunk_fts WHERE chunk_fts MATCH 'UNIQUE_KW_001'")
            ).fetchall()
            assert len(stale_rows) == 0

            doc_row = session.execute(
                text(
                    "SELECT parse_status, size_bytes "
                    "FROM documents WHERE path LIKE '%report_001.txt'"
                )
            ).fetchone()
            assert doc_row is not None
            assert doc_row[0] == "failed"
            assert doc_row[1] == 0

            chunk_count = session.execute(
                text(
                    "SELECT COUNT(*) FROM chunks c "
                    "JOIN documents d ON c.doc_id = d.doc_id "
                    "WHERE d.path LIKE '%report_001.txt'"
                )
            ).scalar()
            assert chunk_count == 0

    def test_hash_failure_retries_on_unchanged_content(
        self,
        source_service: SourceService,
        index_service: IndexService,
        engine: Engine,
        corpus_copy: Path,
        monkeypatch,
    ) -> None:
        from opendocs.indexing import index_builder as index_builder_module

        source = source_service.add_source(corpus_copy)
        index_service.full_index_source(source.source_root_id)

        target = (corpus_copy / "report_001.txt").resolve()
        real_compute_hash = index_builder_module._compute_hash

        def flaky_compute_hash(file_path: Path) -> str:
            if Path(file_path).resolve() == target:
                raise OSError("simulated hash failure")
            return real_compute_hash(file_path)

        monkeypatch.setattr(index_builder_module, "_compute_hash", flaky_compute_hash)
        failed_result = index_service.update_index_for_changes(source.source_root_id)
        failed_entries = [
            entry for entry in failed_result.results if Path(entry.path).resolve() == target
        ]
        assert len(failed_entries) == 1
        assert failed_entries[0].status == "failed"

        with session_scope(engine) as session:
            failed_doc_row = session.execute(
                text(
                    "SELECT parse_status, hash_sha256, indexed_at FROM documents WHERE path = :path"
                ),
                {"path": str(target)},
            ).one()
            assert failed_doc_row[0] == "failed"
            assert failed_doc_row[1] is None
            assert failed_doc_row[2] is None

        monkeypatch.setattr(index_builder_module, "_compute_hash", real_compute_hash)
        retry_result = index_service.update_index_for_changes(source.source_root_id)
        retry_entries = [
            entry for entry in retry_result.results if Path(entry.path).resolve() == target
        ]
        assert len(retry_entries) == 1
        assert retry_entries[0].status == "success"

        with session_scope(engine) as session:
            doc_row = session.execute(
                text(
                    "SELECT parse_status, hash_sha256, indexed_at FROM documents WHERE path = :path"
                ),
                {"path": str(target)},
            ).one()
            assert doc_row[0] == "success"
            assert doc_row[1] is not None
            assert doc_row[2] is not None

            chunk_count = session.execute(
                text(
                    "SELECT COUNT(*) FROM chunks c "
                    "JOIN documents d ON c.doc_id = d.doc_id "
                    "WHERE d.path = :path"
                ),
                {"path": str(target)},
            ).scalar()
            assert chunk_count > 0

    def test_incremental_audit_logged(
        self,
        source_service: SourceService,
        index_service: IndexService,
        engine: Engine,
        corpus_copy: Path,
    ) -> None:
        """TC-003: incremental update produces index_incremental audit with detail."""
        source = source_service.add_source(corpus_copy)
        index_service.full_index_source(source.source_root_id)

        new_file = corpus_copy / "audit_test_incr.txt"
        new_file.write_text("Audit test for incremental.")

        index_service.update_index_for_changes(source.source_root_id)

        with session_scope(engine) as session:
            audits = AuditRepository(session).query(
                target_type="index_run",
            )
            incr_audits = [a for a in audits if a.operation == "index_incremental"]
            assert len(incr_audits) >= 1
            audit = incr_audits[0]
            linked_scan_run = session.execute(
                text(
                    "SELECT scan_run_id, trace_id FROM scan_runs WHERE scan_run_id = :scan_run_id"
                ),
                {"scan_run_id": audit.target_id},
            ).one()
            assert audit.trace_id  # non-empty trace_id
            assert audit.target_id == audit.detail_json["scan_run_id"]
            assert audit.trace_id == linked_scan_run[1]
            detail = audit.detail_json
            assert detail["source_root_id"] == source.source_root_id
            assert detail["scan_run_id"] == linked_scan_run[0]
            assert "total" in detail
            assert "success" in detail
            assert "failed" in detail
            assert detail["total"] >= 1

    def test_incremental_scan_creates_scan_run(
        self,
        source_service: SourceService,
        index_service: IndexService,
        engine: Engine,
        corpus_copy: Path,
    ) -> None:
        """S3-T01: incremental scans should also persist scan_run records."""
        source = source_service.add_source(corpus_copy)
        index_service.full_index_source(source.source_root_id)

        with session_scope(engine) as session:
            before = session.execute(text("SELECT COUNT(*) FROM scan_runs")).scalar()

        (corpus_copy / "scan_run_incremental.txt").write_text("incremental scan run")
        index_service.update_index_for_changes(source.source_root_id)

        with session_scope(engine) as session:
            after = session.execute(text("SELECT COUNT(*) FROM scan_runs")).scalar()
            latest = session.execute(
                text(
                    "SELECT source_root_id, status, trace_id "
                    "FROM scan_runs ORDER BY started_at DESC LIMIT 1"
                )
            ).one()

        assert after == before + 1
        assert latest[0] == source.source_root_id
        assert latest[1] == "completed"
        assert latest[2]


# ---------------------------------------------------------------------------
# TC-004: Deleted file no longer in search results
# ---------------------------------------------------------------------------


class TestTC004:
    """TC-004: deleted file marked is_deleted_from_fs, not in FTS."""

    def test_deleted_file_marked(
        self,
        source_service: SourceService,
        index_service: IndexService,
        engine: Engine,
        corpus_copy: Path,
    ) -> None:
        source = source_service.add_source(corpus_copy)
        index_service.full_index_source(source.source_root_id)

        # Confirm report_001.txt is indexed
        with session_scope(engine) as session:
            row = session.execute(
                text("SELECT chunk_id FROM chunk_fts WHERE chunk_fts MATCH 'UNIQUE_KW_001'")
            ).fetchall()
            assert len(row) >= 1

        # Delete the file
        target = corpus_copy / "report_001.txt"
        target.unlink()

        index_service.update_index_for_changes(source.source_root_id)

        # Document should be marked as deleted
        with session_scope(engine) as session:
            deleted = session.execute(
                text("SELECT is_deleted_from_fs FROM documents WHERE path LIKE '%report_001%'")
            ).fetchone()
            assert deleted is not None
            assert deleted[0] == 1  # True

    def test_deleted_file_not_in_fts(
        self,
        source_service: SourceService,
        index_service: IndexService,
        engine: Engine,
        corpus_copy: Path,
    ) -> None:
        source = source_service.add_source(corpus_copy)
        index_service.full_index_source(source.source_root_id)

        target = corpus_copy / "report_001.txt"
        target.unlink()

        index_service.update_index_for_changes(source.source_root_id)

        with session_scope(engine) as session:
            rows = session.execute(
                text("SELECT chunk_id FROM chunk_fts WHERE chunk_fts MATCH 'UNIQUE_KW_001'")
            ).fetchall()
            assert len(rows) == 0

    def test_scan_errors_do_not_soft_delete_existing_documents(
        self,
        source_service: SourceService,
        index_service: IndexService,
        engine: Engine,
        corpus_copy: Path,
        monkeypatch,
    ) -> None:
        """FR-001: unreadable files should stay indexed until a real delete is observed."""
        source = source_service.add_source(corpus_copy)
        index_service.full_index_source(source.source_root_id)

        target = (corpus_copy / "report_001.txt").resolve()

        def fake_scan(*args, **kwargs) -> ScanResult:
            return ScanResult(
                source_root_id=source.source_root_id,
                source_root_path=str(corpus_copy),
                included=[],
                errors=[(str(target), "permission denied")],
                duration_sec=0.01,
            )

        monkeypatch.setattr(index_service._source_service._scanner, "scan", fake_scan)
        index_service.update_index_for_changes(source.source_root_id)

        with session_scope(engine) as session:
            doc_row = session.execute(
                text("SELECT is_deleted_from_fs, parse_status FROM documents WHERE path = :path"),
                {"path": str(target)},
            ).one()
            chunk_count = session.execute(
                text(
                    "SELECT COUNT(*) FROM chunks c "
                    "JOIN documents d ON c.doc_id = d.doc_id "
                    "WHERE d.path = :path"
                ),
                {"path": str(target)},
            ).scalar()

        assert doc_row[0] == 0
        assert doc_row[1] == "success"
        assert chunk_count > 0

    def test_incremental_reindex_preserves_document_source_path(
        self,
        source_service: SourceService,
        index_service: IndexService,
        engine: Engine,
        corpus_copy: Path,
    ) -> None:
        """Document provenance must stay file-scoped after reindexing an existing path."""
        source = source_service.add_source(corpus_copy)
        index_service.full_index_source(source.source_root_id)

        target = (corpus_copy / "report_001.txt").resolve()

        with session_scope(engine) as session:
            before = session.execute(
                text("SELECT path, source_path FROM documents WHERE path = :path"),
                {"path": str(target)},
            ).one()

        target.write_text("UPDATED CONTENT UNIQUE_KW_SOURCE_PATH_001", encoding="utf-8")
        index_service.update_index_for_changes(source.source_root_id)

        with session_scope(engine) as session:
            after = session.execute(
                text("SELECT path, source_path FROM documents WHERE path = :path"),
                {"path": str(target)},
            ).one()

        assert before == (str(target), str(target))
        assert after == (str(target), str(target))

    def test_incremental_rename_preserves_doc_identity_and_initial_source_path(
        self,
        source_service: SourceService,
        index_service: IndexService,
        engine: Engine,
        corpus_copy: Path,
    ) -> None:
        source = source_service.add_source(corpus_copy)
        index_service.full_index_source(source.source_root_id)

        original = (corpus_copy / "report_002.txt").resolve()
        renamed = (corpus_copy / "report_002_renamed.txt").resolve()

        with session_scope(engine) as session:
            before = session.execute(
                text(
                    "SELECT doc_id, path, source_path, file_identity, is_deleted_from_fs "
                    "FROM documents WHERE path = :path"
                ),
                {"path": str(original)},
            ).one()

        original.rename(renamed)
        result = index_service.update_index_for_changes(source.source_root_id)

        rename_results = [r for r in result.results if Path(r.path).resolve() == renamed]
        assert len(rename_results) == 1
        assert rename_results[0].doc_id == before[0]
        assert rename_results[0].status in {"success", "partial"}

        with session_scope(engine) as session:
            after = session.execute(
                text(
                    "SELECT doc_id, path, source_path, file_identity, is_deleted_from_fs "
                    "FROM documents WHERE doc_id = :doc_id"
                ),
                {"doc_id": before[0]},
            ).one()
            old_path_count = session.execute(
                text("SELECT COUNT(*) FROM documents WHERE path = :path"),
                {"path": str(original)},
            ).scalar()

        assert after[0] == before[0]
        assert after[1] == str(renamed)
        assert after[2] == str(original)
        assert after[3] == before[3]
        assert after[4] == 0
        assert old_path_count == 0

    def test_incremental_path_reuse_creates_new_lineage_without_corrupting_old_one(
        self,
        source_service: SourceService,
        index_service: IndexService,
        engine: Engine,
        corpus_copy: Path,
    ) -> None:
        source = source_service.add_source(corpus_copy)
        index_service.full_index_source(source.source_root_id)

        original = (corpus_copy / "report_002.txt").resolve()
        archived = (corpus_copy / "zzz_report_002_archived.txt").resolve()

        with session_scope(engine) as session:
            before = session.execute(
                text(
                    "SELECT doc_id, path, source_path, file_identity "
                    "FROM documents WHERE path = :path AND is_deleted_from_fs = 0"
                ),
                {"path": str(original)},
            ).one()

        assert before[3] is not None

        original.rename(archived)
        original.write_text("UNIQUE_PATH_REUSE_001 brand new document", encoding="utf-8")

        result = index_service.update_index_for_changes(source.source_root_id)
        changed_paths = {Path(item.path).resolve() for item in result.results}
        assert original in changed_paths
        assert archived in changed_paths

        with session_scope(engine) as session:
            old_lineage = session.execute(
                text(
                    "SELECT doc_id, path, source_path, file_identity, is_deleted_from_fs "
                    "FROM documents WHERE doc_id = :doc_id"
                ),
                {"doc_id": before[0]},
            ).one()
            new_lineage = session.execute(
                text(
                    "SELECT doc_id, path, source_path, file_identity, is_deleted_from_fs "
                    "FROM documents WHERE path = :path AND is_deleted_from_fs = 0"
                ),
                {"path": str(original)},
            ).one()

        assert old_lineage[0] == before[0]
        assert old_lineage[1] == str(archived)
        assert old_lineage[2] == str(original)
        assert old_lineage[3] == before[3]
        assert old_lineage[4] == 0

        assert new_lineage[0] != before[0]
        assert new_lineage[1] == str(original)
        assert new_lineage[2] == str(original)
        assert new_lineage[3] is not None
        assert new_lineage[3] != before[3]
        assert new_lineage[4] == 0

    def test_deleted_lineage_does_not_resurrect_when_file_identity_is_reused(
        self,
        source_service: SourceService,
        index_service: IndexService,
        engine: Engine,
        corpus_copy: Path,
    ) -> None:
        source = source_service.add_source(corpus_copy)

        new_path = (corpus_copy / "identity_reused_new.md").resolve()
        new_path.write_text("# Fresh\n\nUNIQUE_IDENTITY_REUSE_001", encoding="utf-8")
        stat_result = new_path.stat()
        file_identity = _derive_file_identity(stat_result)
        assert file_identity is not None

        old_path = (corpus_copy / "identity_reused_old.md").resolve()
        old_relative_path = old_path.relative_to(corpus_copy.resolve()).as_posix()
        old_directory_path, old_relative_directory_path = derive_directory_facts(
            str(old_path),
            old_relative_path,
        )
        old_doc_id = str(uuid.uuid4())

        with session_scope(engine) as session:
            session.execute(
                text(
                    "INSERT INTO documents ("
                    "doc_id, path, relative_path, display_path, directory_path, "
                    "relative_directory_path, file_identity, source_root_id, source_path, "
                    "source_config_rev, hash_sha256, title, file_type, size_bytes, "
                    "created_at, modified_at, indexed_at, parse_status, category, "
                    "tags_json, sensitivity, is_deleted_from_fs"
                    ") VALUES ("
                    ":doc_id, :path, :relative_path, :display_path, :directory_path, "
                    ":relative_directory_path, :file_identity, :source_root_id, :source_path, "
                    ":source_config_rev, :hash_sha256, :title, :file_type, :size_bytes, "
                    ":created_at, :modified_at, :indexed_at, :parse_status, :category, "
                    ":tags_json, :sensitivity, :is_deleted_from_fs"
                    ")"
                ),
                {
                    "doc_id": old_doc_id,
                    "path": str(old_path),
                    "relative_path": old_relative_path,
                    "display_path": build_display_path(source.display_root, old_relative_path),
                    "directory_path": old_directory_path,
                    "relative_directory_path": old_relative_directory_path,
                    "file_identity": file_identity,
                    "source_root_id": source.source_root_id,
                    "source_path": str(old_path),
                    "source_config_rev": 1,
                    "hash_sha256": "a" * 64,
                    "title": "old deleted lineage",
                    "file_type": "md",
                    "size_bytes": 10,
                    "created_at": "2026-03-01 00:00:00",
                    "modified_at": "2026-03-01 00:00:00",
                    "indexed_at": "2026-03-01 00:00:00",
                    "parse_status": "success",
                    "category": None,
                    "tags_json": "[]",
                    "sensitivity": "internal",
                    "is_deleted_from_fs": 1,
                },
            )

        result = index_service.update_index_for_changes(source.source_root_id)
        new_results = [item for item in result.results if Path(item.path).resolve() == new_path]
        assert len(new_results) == 1
        assert new_results[0].status == "success"
        assert new_results[0].doc_id != old_doc_id

        with session_scope(engine) as session:
            old_lineage = session.execute(
                text(
                    "SELECT doc_id, path, source_path, file_identity, is_deleted_from_fs "
                    "FROM documents WHERE doc_id = :doc_id"
                ),
                {"doc_id": old_doc_id},
            ).one()
            new_lineage = session.execute(
                text(
                    "SELECT doc_id, path, source_path, file_identity, is_deleted_from_fs "
                    "FROM documents WHERE path = :path AND is_deleted_from_fs = 0"
                ),
                {"path": str(new_path)},
            ).one()

        assert old_lineage[0] == old_doc_id
        assert old_lineage[1] == str(old_path)
        assert old_lineage[2] == str(old_path)
        assert old_lineage[3] == file_identity
        assert old_lineage[4] == 1

        assert new_lineage[0] != old_doc_id
        assert new_lineage[1] == str(new_path)
        assert new_lineage[2] == str(new_path)
        assert new_lineage[3] == file_identity
        assert new_lineage[4] == 0
