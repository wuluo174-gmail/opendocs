"""Watcher integration tests: debounce, create/modify/delete events."""

from __future__ import annotations

import threading
import time
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Engine

from opendocs.app.index_service import IndexService
from opendocs.app.source_service import SourceService
from opendocs.storage.db import session_scope
from opendocs.storage.repositories import AuditRepository


class TestWatcher:
    """Watcher detects filesystem changes and triggers indexing."""

    def test_watcher_detects_new_file(
        self,
        source_service: SourceService,
        index_service: IndexService,
        engine: Engine,
        corpus_copy: Path,
    ) -> None:
        source = source_service.add_source(corpus_copy)
        index_service.full_index_source(source.source_root_id)

        status = index_service.start_watching_active_sources(debounce_seconds=0.3)
        assert status.watcher_running is True

        try:
            new_file = corpus_copy / "watcher_new.txt"
            new_file.write_text("UNIQUE_KW_WATCHER_NEW content.")
            # Wait for debounce + processing
            time.sleep(2.0)
        finally:
            index_service.stop_watching()

        with session_scope(engine) as session:
            rows = session.execute(
                text("SELECT chunk_id FROM chunk_fts WHERE chunk_fts MATCH 'UNIQUE_KW_WATCHER_NEW'")
            ).fetchall()
            assert len(rows) >= 1

    def test_watcher_detects_deletion(
        self,
        source_service: SourceService,
        index_service: IndexService,
        engine: Engine,
        corpus_copy: Path,
    ) -> None:
        source = source_service.add_source(corpus_copy)
        index_service.full_index_source(source.source_root_id)

        # Confirm file is indexed
        with session_scope(engine) as session:
            before = session.execute(
                text("SELECT chunk_id FROM chunk_fts WHERE chunk_fts MATCH 'UNIQUE_KW_002'")
            ).fetchall()
            assert len(before) >= 1

        status = index_service.start_watching_active_sources(debounce_seconds=0.3)
        assert status.watcher_running is True

        try:
            target = corpus_copy / "report_002.txt"
            target.unlink()
            time.sleep(2.0)
        finally:
            index_service.stop_watching()

        with session_scope(engine) as session:
            after = session.execute(
                text("SELECT chunk_id FROM chunk_fts WHERE chunk_fts MATCH 'UNIQUE_KW_002'")
            ).fetchall()
            assert len(after) == 0

    def test_watcher_detects_modification(
        self,
        source_service: SourceService,
        index_service: IndexService,
        engine: Engine,
        corpus_copy: Path,
    ) -> None:
        """S3-T05: watcher detects file modification and updates index."""
        source = source_service.add_source(corpus_copy)
        index_service.full_index_source(source.source_root_id)

        status = index_service.start_watching_active_sources(debounce_seconds=0.3)
        assert status.watcher_running is True

        try:
            target = corpus_copy / "report_003.txt"
            target.write_text("MODIFIED BY WATCHER UNIQUE_KW_WATCHER_MOD content.")
            time.sleep(2.0)
        finally:
            index_service.stop_watching()

        with session_scope(engine) as session:
            rows = session.execute(
                text("SELECT chunk_id FROM chunk_fts WHERE chunk_fts MATCH 'UNIQUE_KW_WATCHER_MOD'")
            ).fetchall()
            assert len(rows) >= 1

    def test_watcher_rename_preserves_doc_identity_and_initial_source_path(
        self,
        source_service: SourceService,
        index_service: IndexService,
        engine: Engine,
        corpus_copy: Path,
    ) -> None:
        source = source_service.add_source(corpus_copy)
        index_service.full_index_source(source.source_root_id)

        original = (corpus_copy / "report_003.txt").resolve()
        renamed = (corpus_copy / "report_003_watcher_renamed.txt").resolve()

        with session_scope(engine) as session:
            before = session.execute(
                text(
                    "SELECT doc_id, path, source_path, file_identity "
                    "FROM documents WHERE path = :path"
                ),
                {"path": str(original)},
            ).one()

        status = index_service.start_watching_active_sources(debounce_seconds=0.3)
        assert status.watcher_running is True

        try:
            original.rename(renamed)
            time.sleep(2.0)
        finally:
            index_service.stop_watching()

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

    def test_watcher_audit_logged(
        self,
        source_service: SourceService,
        index_service: IndexService,
        engine: Engine,
        corpus_copy: Path,
    ) -> None:
        """TC-003: watcher audit is queryable by canonical file path."""
        source = source_service.add_source(corpus_copy)
        index_service.full_index_source(source.source_root_id)

        status = index_service.start_watching_active_sources(debounce_seconds=0.3)
        assert status.watcher_running is True

        try:
            new_file = corpus_copy / "watcher_audit_test.txt"
            new_file.write_text("Audit test for watcher event.")
            expected_path = str(new_file.resolve())
            time.sleep(2.0)
        finally:
            index_service.stop_watching()

        with session_scope(engine) as session:
            audits = AuditRepository(session).query(
                target_type="source",
                file_path=expected_path,
            )
            watcher_audits = [a for a in audits if a.operation == "watcher_event"]
            assert len(watcher_audits) >= 1
            audit = watcher_audits[0]
            assert audit.trace_id  # non-empty
            assert audit.target_id == source.source_root_id
            assert audit.result == "success"
            detail = audit.detail_json
            assert detail["file_path"] == expected_path
            assert detail["event_type"] in ("created", "modified")
            assert detail["status"] in ("success", "skipped", "partial")
            assert detail["document_id"]

    def test_watcher_delete_not_found_audit_logged(
        self,
        source_service: SourceService,
        index_service: IndexService,
        engine: Engine,
        corpus_copy: Path,
    ) -> None:
        """TC-004: deleted miss still writes a canonical watcher audit record."""
        source = source_service.add_source(corpus_copy)
        index_service.full_index_source(source.source_root_id)

        status = index_service.start_watching_active_sources(debounce_seconds=0.3)
        assert status.watcher_running is True

        try:
            transient = corpus_copy / "watcher_delete_not_found.txt"
            transient.write_text("Transient watcher file.")
            expected_path = str(transient.resolve())
            time.sleep(0.1)
            transient.unlink()
            time.sleep(2.0)
        finally:
            index_service.stop_watching()

        with session_scope(engine) as session:
            audits = AuditRepository(session).query(
                target_type="source",
                file_path=expected_path,
            )
            deleted_audits = [
                a
                for a in audits
                if a.operation == "watcher_event" and a.detail_json.get("event_type") == "deleted"
            ]
            assert len(deleted_audits) >= 1
            audit = deleted_audits[0]
            assert audit.trace_id
            assert audit.target_id == source.source_root_id
            assert audit.result == "success"
            detail = audit.detail_json
            assert detail["file_path"] == expected_path
            assert detail["event_type"] == "deleted"
            assert detail["status"] == "not_found"
            assert detail["document_id"] is None

    def test_watcher_start_stop(
        self,
        source_service: SourceService,
        corpus_copy: Path,
        index_service: IndexService,
    ) -> None:
        source_service.add_source(corpus_copy)
        started = index_service.start_watching_active_sources(debounce_seconds=0.3)
        assert started.watcher_running is True
        assert str(corpus_copy.resolve()) in started.watched_paths

        running = index_service.get_index_status()
        assert running.watcher_running is True
        assert running.watched_source_count == 1

        index_service.stop_watching()
        stopped = index_service.get_index_status()
        assert stopped.watcher_running is False
        assert stopped.watched_source_count == 0

    def test_watcher_serializes_index_mutations(
        self,
        source_service: SourceService,
        index_service: IndexService,
        engine: Engine,
        corpus_copy: Path,
        monkeypatch,
    ) -> None:
        """Watcher events must be processed by a single writer, never in parallel."""
        source = source_service.add_source(corpus_copy)
        index_service.full_index_source(source.source_root_id)

        status = index_service.start_watching_active_sources(debounce_seconds=0.1)
        assert status.watcher_running is True
        watcher = index_service._watcher
        assert watcher is not None

        active_calls = 0
        max_active_calls = 0
        counters_lock = threading.Lock()
        original_index_file = watcher._builder.index_file

        def wrapped_index_file(*args, **kwargs):
            nonlocal active_calls, max_active_calls
            with counters_lock:
                active_calls += 1
                max_active_calls = max(max_active_calls, active_calls)
            try:
                time.sleep(0.15)
                return original_index_file(*args, **kwargs)
            finally:
                with counters_lock:
                    active_calls -= 1

        monkeypatch.setattr(watcher._builder, "index_file", wrapped_index_file)

        try:
            for suffix in ("a", "b", "c"):
                new_file = corpus_copy / f"watcher_serial_{suffix}.txt"
                new_file.write_text(f"UNIQUE_KW_WATCHER_SERIAL_{suffix.upper()} content.")
            time.sleep(3.0)
        finally:
            index_service.stop_watching()

        assert max_active_calls == 1
        with session_scope(engine) as session:
            for suffix in ("A", "B", "C"):
                rows = session.execute(
                    text(
                        "SELECT chunk_id FROM chunk_fts "
                        f"WHERE chunk_fts MATCH 'UNIQUE_KW_WATCHER_SERIAL_{suffix}'"
                    )
                ).fetchall()
                assert len(rows) >= 1
