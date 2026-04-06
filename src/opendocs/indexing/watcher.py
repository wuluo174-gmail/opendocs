"""Watchdog-based file system monitor with serialized event processing."""

from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from queue import Queue
from typing import Any, Literal

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from opendocs.indexing.scanner import (
    _EXT_TO_TYPE,
    ExcludeRules,
    ScannedFile,
    _derive_file_identity,
    _get_file_birth_time,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _WatcherEvent:
    """Normalized watcher event owned by the runtime event queue."""

    kind: Literal["index", "delete", "stop"]
    source_root_id: str
    path: str
    event_type: str
    scanned: ScannedFile | None = None


class _DebouncedHandler(FileSystemEventHandler):
    """Debounce watchdog events per path with a configurable delay."""

    def __init__(
        self,
        callback_index: Any,
        callback_delete: Any,
        *,
        registry: Any,
        exclude_rules: ExcludeRules,
        source_root_id: str,
        root_path: Path,
        debounce_seconds: float = 1.0,
    ) -> None:
        super().__init__()
        self._callback_index = callback_index
        self._callback_delete = callback_delete
        self._registry = registry
        self._rules = exclude_rules
        self._source_root_id = source_root_id
        self._root_path = root_path
        self._debounce = debounce_seconds
        self._timers: dict[str, threading.Timer] = {}
        self._lock = threading.Lock()

    def on_created(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._schedule(event.src_path, "created")

    def on_modified(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._schedule(event.src_path, "modified")

    def on_deleted(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._schedule(event.src_path, "deleted")

    def on_moved(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            if hasattr(event, "dest_path"):
                self._schedule_move(event.src_path, event.dest_path)
            else:
                self._schedule(event.src_path, "deleted")

    def _schedule(self, path: str, event_type: str) -> None:
        with self._lock:
            existing = self._timers.pop(path, None)
            if existing is not None:
                existing.cancel()
            timer = threading.Timer(
                self._debounce,
                self._process,
                args=(path, path, event_type),
            )
            timer.daemon = True
            self._timers[path] = timer
            timer.start()

    def _schedule_move(self, src_path: str, dest_path: str) -> None:
        move_key = f"move:{src_path}->{dest_path}"
        with self._lock:
            for key in (src_path, dest_path, move_key):
                existing = self._timers.pop(key, None)
                if existing is not None:
                    existing.cancel()
            timer = threading.Timer(
                self._debounce,
                self._process_move,
                args=(move_key, src_path, dest_path),
            )
            timer.daemon = True
            self._timers[move_key] = timer
            timer.start()

    def _process(self, timer_key: str, path_str: str, event_type: str) -> None:
        with self._lock:
            self._timers.pop(timer_key, None)

        try:
            p = Path(path_str)

            if event_type == "deleted":
                self._callback_delete(path_str)
                return

            scanned = self._build_scanned_file(p)
            if scanned is None:
                return
            self._callback_index(scanned, event_type)

        except Exception:
            logger.exception("Error processing watcher event for %s", path_str)

    def _process_move(self, timer_key: str, src_path: str, dest_path: str) -> None:
        with self._lock:
            self._timers.pop(timer_key, None)

        try:
            scanned = self._build_scanned_file(Path(dest_path))
            if scanned is None:
                self._callback_delete(src_path)
                return
            self._callback_index(scanned, "moved")
        except Exception:
            logger.exception("Error processing watcher move from %s to %s", src_path, dest_path)

    def _build_scanned_file(self, path: Path) -> ScannedFile | None:
        if not path.exists():
            return None
        resolved = path.resolve()
        if not resolved.is_relative_to(self._root_path):
            return None
        if self._rules.should_exclude_file(resolved.name, 0):
            return None

        ext = resolved.suffix.lower()
        file_type = _EXT_TO_TYPE.get(ext, "unsupported")
        if file_type == "unsupported" or not self._registry.is_supported(resolved):
            return None

        stat = resolved.stat()
        if self._rules.should_exclude_file(resolved.name, stat.st_size):
            return None

        return ScannedFile(
            path=resolved,
            relative_path=str(resolved.relative_to(self._root_path)),
            size_bytes=stat.st_size,
            created_at=_get_file_birth_time(stat),
            modified_at=datetime.fromtimestamp(stat.st_mtime),
            file_identity=_derive_file_identity(stat),
            file_type=file_type,
        )

    def cancel_all(self) -> None:
        with self._lock:
            for timer in self._timers.values():
                timer.cancel()
            self._timers.clear()


class IndexWatcher:
    """Monitor source directories and trigger serialized incremental indexing."""

    def __init__(
        self,
        engine: Any,
        index_builder: Any,
        registry: Any,
        *,
        debounce_seconds: float = 1.0,
    ) -> None:
        self._engine = engine
        self._builder = index_builder
        self._registry = registry
        self._debounce = debounce_seconds
        self._observer: Observer | None = None
        self._worker: threading.Thread | None = None
        self._event_queue: Queue[_WatcherEvent] = Queue()
        self._handlers: list[_DebouncedHandler] = []
        self._watched_paths: list[str] = []
        self._watched_source_ids: list[str] = []

    def start(self, sources: list[Any]) -> int:
        """Start watching all active source roots."""
        if self._observer is not None:
            return len(self._watched_paths)

        self._observer = Observer()
        for source in sources:
            root = Path(source.path).resolve()
            if not root.exists():
                logger.warning("Source root does not exist, skipping watch: %s", root)
                continue

            rules = ExcludeRules.model_validate(source.exclude_rules_json or {})

            handler = _DebouncedHandler(
                callback_index=lambda scanned, et, src=source: self._enqueue_file_changed(
                    scanned,
                    source_root_id=src.source_root_id,
                    event_type=et,
                ),
                callback_delete=lambda path, src=source: self._enqueue_file_deleted(
                    path,
                    source_root_id=src.source_root_id,
                ),
                registry=self._registry,
                exclude_rules=rules,
                source_root_id=source.source_root_id,
                root_path=root,
                debounce_seconds=self._debounce,
            )
            self._handlers.append(handler)
            self._observer.schedule(handler, str(root), recursive=source.recursive)
            self._watched_paths.append(str(root))
            self._watched_source_ids.append(source.source_root_id)

        if not self._handlers:
            self._observer = None
            logger.info("IndexWatcher skipped: no readable active sources to watch")
            return 0

        self._start_worker()
        self._observer.start()
        logger.info("IndexWatcher started for %d sources", len(self._watched_paths))
        return len(self._watched_paths)

    def stop(self) -> None:
        if self._observer is not None:
            for h in self._handlers:
                h.cancel_all()
            self._observer.stop()
            self._observer.join(timeout=5)
            self._observer = None
        self._stop_worker()
        self._handlers.clear()
        self._watched_paths.clear()
        self._watched_source_ids.clear()
        logger.info("IndexWatcher stopped")

    def is_running(self) -> bool:
        return (
            self._observer is not None
            and self._observer.is_alive()
            and self._worker is not None
            and self._worker.is_alive()
        )

    @property
    def watched_paths(self) -> tuple[str, ...]:
        return tuple(self._watched_paths)

    @property
    def watched_source_ids(self) -> tuple[str, ...]:
        return tuple(self._watched_source_ids)

    def _start_worker(self) -> None:
        if self._worker is not None and self._worker.is_alive():
            return
        self._worker = threading.Thread(
            target=self._drain_events,
            name="OpenDocsIndexWatcherWorker",
            daemon=True,
        )
        self._worker.start()

    def _stop_worker(self) -> None:
        if self._worker is None:
            self._event_queue = Queue()
            return
        self._event_queue.put(
            _WatcherEvent(
                kind="stop",
                source_root_id="",
                path="",
                event_type="stop",
            )
        )
        self._worker.join(timeout=5)
        self._worker = None
        self._event_queue = Queue()

    def _drain_events(self) -> None:
        while True:
            event = self._event_queue.get()
            try:
                if event.kind == "stop":
                    return
                if event.kind == "index":
                    self._process_file_changed(event)
                elif event.kind == "delete":
                    self._process_file_deleted(event)
            finally:
                self._event_queue.task_done()

    def _enqueue_file_changed(
        self,
        scanned: ScannedFile,
        *,
        source_root_id: str,
        event_type: str,
    ) -> None:
        self._event_queue.put(
            _WatcherEvent(
                kind="index",
                source_root_id=source_root_id,
                path=str(scanned.path),
                event_type=event_type,
                scanned=scanned,
            )
        )

    def _enqueue_file_deleted(self, path_str: str, *, source_root_id: str) -> None:
        self._event_queue.put(
            _WatcherEvent(
                kind="delete",
                source_root_id=source_root_id,
                path=str(Path(path_str).resolve()),
                event_type="deleted",
            )
        )

    def _process_file_changed(self, event: _WatcherEvent) -> None:
        scanned = event.scanned
        if scanned is None:
            return
        trace_id = str(uuid.uuid4())
        status = "unknown"
        document_id: str | None = None
        try:
            result = self._builder.index_file(
                scanned,
                source_root_id=event.source_root_id,
                trace_id=trace_id,
                force=False,
            )
            status = result.status
            document_id = result.doc_id or None
        except Exception:
            status = "error"
            logger.exception("Watcher index failed for %s", scanned.path)

        self._write_watcher_audit(
            path=str(scanned.path),
            source_root_id=event.source_root_id,
            event_type=event.event_type,
            status=status,
            trace_id=trace_id,
            document_id=document_id,
        )

    def _process_file_deleted(self, event: _WatcherEvent) -> None:
        trace_id = str(uuid.uuid4())
        from opendocs.storage.db import session_scope
        from opendocs.storage.repositories import DocumentRepository

        resolved_path = event.path
        status = "not_found"
        doc = None
        document_id: str | None = None
        try:
            with session_scope(self._engine) as session:
                doc_repo = DocumentRepository(session)
                doc = doc_repo.get_by_path(resolved_path)
                if doc is not None:
                    doc_id = doc.doc_id
                    document_id = doc_id

            if doc is not None:
                removed = self._builder.remove_document(
                    doc_id,
                    trace_id=trace_id,
                    soft_delete=True,
                    expected_path=resolved_path,
                )
                status = "success" if removed else "not_found"
        except Exception:
            status = "error"
            logger.exception("Watcher delete failed for %s", resolved_path)

        self._write_watcher_audit(
            path=resolved_path,
            source_root_id=event.source_root_id,
            event_type="deleted",
            status=status,
            trace_id=trace_id,
            document_id=document_id,
        )

    def _write_watcher_audit(
        self,
        *,
        path: str,
        source_root_id: str,
        event_type: str,
        status: str,
        trace_id: str,
        document_id: str | None = None,
    ) -> None:
        """Write a watcher_event audit record (best-effort, never throws)."""
        try:
            from opendocs.app._audit_helpers import (
                build_file_audit_detail,
                create_audit_record,
                flush_audit_to_jsonl,
                normalize_audit_path,
            )
            from opendocs.storage.db import session_scope

            normalized_path = normalize_audit_path(path)
            audit_record = None
            with session_scope(self._engine) as session:
                audit_record = create_audit_record(
                    session,
                    actor="system",
                    operation="watcher_event",
                    target_type="source",
                    target_id=source_root_id,
                    result="failure" if status == "error" else "success",
                    detail_json=build_file_audit_detail(
                        normalized_path,
                        event_type=event_type,
                        status=status,
                        document_id=document_id,
                    ),
                    trace_id=trace_id,
                )
            if audit_record is not None:
                flush_audit_to_jsonl(audit_record)
        except Exception:
            logger.warning("Failed to write watcher_event audit for %s", path)
