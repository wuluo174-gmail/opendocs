"""Index build pipeline: parse → hash → chunk → persist → HNSW."""

from __future__ import annotations

import hashlib
import logging
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy.engine import Engine

from opendocs.app._audit_helpers import (
    build_file_audit_detail,
    create_audit_record,
    flush_audit_to_jsonl,
)
from opendocs.domain.document_metadata import DocumentMetadata, merge_document_metadata
from opendocs.domain.models import AuditLogModel, ChunkModel, DocumentModel, SourceRootModel
from opendocs.indexing.chunker import ChunkConfig, Chunker, ChunkResult
from opendocs.indexing.hnsw_manager import HnswManager
from opendocs.indexing.scanner import ScannedFile
from opendocs.parsers.base import ParsedDocument, ParserRegistry
from opendocs.storage.db import session_scope
from opendocs.storage.repositories import ChunkRepository, DocumentRepository
from opendocs.utils.path_facts import build_display_path, derive_directory_facts

logger = logging.getLogger(__name__)


@dataclass
class IndexedFileResult:
    path: str
    doc_id: str
    status: str  # "success" | "partial" | "failed" | "skipped"
    chunk_count: int = 0
    error_info: str | None = None


@dataclass
class IndexBatchResult:
    total: int = 0
    success_count: int = 0
    partial_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    results: list[IndexedFileResult] = field(default_factory=list)
    duration_sec: float = 0.0
    hnsw_status: str = "synced"  # "synced" | "degraded"


@dataclass
class DocumentResolution:
    existing: DocumentModel | None
    displaced: DocumentModel | None = None


@dataclass(frozen=True)
class ActiveDocumentSnapshot:
    doc_id: str
    path: str
    file_identity: str | None


@dataclass
class BatchResolutionState:
    """Resolve the next active document set from one full scan snapshot.

    The source of truth for incremental reconciliation is:
    1. the previous active document set persisted in SQLite
    2. the current scan result for this source root

    We snapshot the previous active set once per batch so lineage resolution
    does not depend on per-file processing order. This prevents path reuse
    from breaking rename/move reconciliation.
    """

    previous_by_path: dict[str, ActiveDocumentSnapshot]
    previous_by_identity: dict[str, ActiveDocumentSnapshot]
    claimed_doc_ids: set[str] = field(default_factory=set)

    @classmethod
    def build(cls, active_documents: list[DocumentModel]) -> BatchResolutionState:
        snapshots = [
            ActiveDocumentSnapshot(
                doc_id=document.doc_id,
                path=document.path,
                file_identity=document.file_identity,
            )
            for document in active_documents
        ]
        previous_by_path = {snapshot.path: snapshot for snapshot in snapshots}
        previous_by_identity = {
            snapshot.file_identity: snapshot
            for snapshot in snapshots
            if snapshot.file_identity is not None
        }
        return cls(
            previous_by_path=previous_by_path,
            previous_by_identity=previous_by_identity,
        )

    def claim(self, doc_id: str) -> None:
        self.claimed_doc_ids.add(doc_id)

    def match_by_path(self, path: str) -> ActiveDocumentSnapshot | None:
        snapshot = self.previous_by_path.get(path)
        if snapshot is None or snapshot.doc_id in self.claimed_doc_ids:
            return None
        return snapshot

    def match_by_identity(self, file_identity: str | None) -> ActiveDocumentSnapshot | None:
        if file_identity is None:
            return None
        snapshot = self.previous_by_identity.get(file_identity)
        if snapshot is None or snapshot.doc_id in self.claimed_doc_ids:
            return None
        return snapshot


def _compute_hash(file_path: Path) -> str:
    return hashlib.sha256(file_path.read_bytes()).hexdigest()


def _to_chunk_model(cr: ChunkResult) -> ChunkModel:
    return ChunkModel(
        chunk_id=cr.chunk_id,
        doc_id=cr.doc_id,
        chunk_index=cr.chunk_index,
        text=cr.text,
        char_start=cr.char_start,
        char_end=cr.char_end,
        page_no=cr.page_no,
        paragraph_start=cr.paragraph_start,
        paragraph_end=cr.paragraph_end,
        heading_path=cr.heading_path,
        token_estimate=cr.token_estimate,
        embedding_model=cr.embedding_model,
        embedding_key=cr.embedding_key,
    )


class IndexBuilder:
    """Build and maintain the document index."""

    def __init__(
        self,
        engine: Engine,
        registry: ParserRegistry,
        chunker: Chunker,
        *,
        hnsw_manager: HnswManager | None = None,
        chunk_config: ChunkConfig | None = None,
        embedder: object | None = None,
    ) -> None:
        self._engine = engine
        self._registry = registry
        self._chunker = chunker
        self._hnsw = hnsw_manager
        self._chunk_config = chunk_config
        self._embedder = embedder

    def index_file(
        self,
        scanned: ScannedFile,
        *,
        source_root_id: str,
        trace_id: str,
        force: bool = False,
        resolution_state: BatchResolutionState | None = None,
    ) -> IndexedFileResult:
        """Index a single file. Three-phase: SQLite txn → JSONL → HNSW."""
        audit_records: list[AuditLogModel] = []
        new_chunk_ids: list[str] = []
        old_chunk_ids: list[str] = []
        result: IndexedFileResult | None = None
        doc_id = ""

        # === Phase A: SQLite transaction (strong consistency) ===
        with session_scope(self._engine) as session:
            doc_repo = DocumentRepository(session)
            chunk_repo = ChunkRepository(session)
            source = self._require_source_root(session, source_root_id)
            source_defaults = self._source_defaults(source)
            resolution = self._resolve_existing_document(
                doc_repo,
                scanned,
                resolution_state=resolution_state,
            )
            existing = resolution.existing
            if resolution_state is not None and existing is not None:
                resolution_state.claim(existing.doc_id)
            doc_id = existing.doc_id if existing else str(uuid.uuid4())
            old_chunk_ids.extend(
                self._retire_displaced_document(
                    session,
                    doc_repo,
                    chunk_repo,
                    displaced=resolution.displaced,
                    replacement_path=str(scanned.path),
                    trace_id=trace_id,
                    audit_records=audit_records,
                )
            )

            try:
                file_hash = _compute_hash(scanned.path)
            except OSError as exc:
                if existing:
                    old_chunk_ids.extend(
                        c.chunk_id for c in chunk_repo.list_by_document(existing.doc_id)
                    )
                    chunk_repo.delete_by_doc_id(existing.doc_id, allow_delete=True)
                if self._hnsw is not None and old_chunk_ids:
                    self._hnsw.mark_stale(
                        session,
                        embedder=self._embedder,
                        reason="document_hash_failed",
                    )

                parsed = ParsedDocument(
                    file_path=str(scanned.path),
                    file_type=scanned.file_type,
                    raw_text="",
                    title=scanned.path.stem,
                    parse_status="failed",
                    error_info=f"hash error: {exc}",
                )
                doc = self._upsert_document(
                    existing,
                    doc_repo,
                    scanned,
                    None,
                    parsed,
                    merge_document_metadata(
                        source_defaults=source_defaults, declared=parsed.metadata
                    ),
                    source,
                    doc_id,
                )
                audit_records.append(
                    create_audit_record(
                        session,
                        actor="system",
                        operation="index_file",
                        target_type="document",
                        target_id=doc.doc_id,
                        result="failure",
                        detail_json=build_file_audit_detail(
                            scanned.path,
                            error=f"hash error: {exc}",
                            error_stage="hash",
                        ),
                        trace_id=trace_id,
                    )
                )
                result = IndexedFileResult(
                    path=str(scanned.path),
                    doc_id=doc.doc_id,
                    status="failed",
                    error_info=f"hash error: {exc}",
                )

            if result is None:
                if self._can_skip_existing(
                    existing,
                    chunk_repo,
                    scanned=scanned,
                    file_hash=file_hash,
                    source_config_rev=source.source_config_rev,
                    force=force,
                ):
                    # Skip: no changes, normal exit from with → empty commit
                    result = IndexedFileResult(
                        path=str(scanned.path),
                        doc_id=doc_id,
                        status="skipped",
                    )

                else:
                    # Parse the file
                    parsed = self._registry.parse(scanned.path)

                    if parsed.parse_status == "failed":
                        if existing:
                            old_chunk_ids.extend(
                                c.chunk_id for c in chunk_repo.list_by_document(existing.doc_id)
                            )
                            chunk_repo.delete_by_doc_id(existing.doc_id, allow_delete=True)
                        if self._hnsw is not None and old_chunk_ids:
                            self._hnsw.mark_stale(
                                session,
                                embedder=self._embedder,
                                reason="document_parse_failed",
                            )
                        # Record failed document
                        doc = self._upsert_document(
                            existing,
                            doc_repo,
                            scanned,
                            file_hash,
                            parsed,
                            merge_document_metadata(
                                source_defaults=source_defaults,
                                declared=parsed.metadata,
                            ),
                            source,
                            doc_id,
                        )
                        audit_records.append(
                            create_audit_record(
                                session,
                                actor="system",
                                operation="index_file",
                                target_type="document",
                                target_id=doc.doc_id,
                                result="failure",
                                detail_json=build_file_audit_detail(
                                    scanned.path,
                                    error=parsed.error_info or "parse failed",
                                ),
                                trace_id=trace_id,
                            )
                        )
                        result = IndexedFileResult(
                            path=str(scanned.path),
                            doc_id=doc.doc_id,
                            status="failed",
                            error_info=parsed.error_info,
                        )

                    else:
                        # Normal path: parse + chunk + persist
                        chunks = self._chunker.chunk(
                            parsed, config=self._chunk_config, doc_id=doc_id
                        )
                        if existing:
                            old_chunk_ids.extend(
                                c.chunk_id for c in chunk_repo.list_by_document(existing.doc_id)
                            )
                            chunk_repo.delete_by_doc_id(existing.doc_id, allow_delete=True)
                        if self._hnsw is not None and (old_chunk_ids or chunks):
                            self._hnsw.mark_stale(
                                session,
                                embedder=self._embedder,
                                reason="document_reindexed",
                            )
                        doc = self._upsert_document(
                            existing,
                            doc_repo,
                            scanned,
                            file_hash,
                            parsed,
                            merge_document_metadata(
                                source_defaults=source_defaults,
                                declared=parsed.metadata,
                            ),
                            source,
                            doc_id,
                        )
                        for chunk in chunks:
                            chunk_repo.create(_to_chunk_model(chunk))
                            new_chunk_ids.append(chunk.chunk_id)
                        doc_repo.update_indexed_at(doc.doc_id)
                        audit_records.append(
                            create_audit_record(
                                session,
                                actor="system",
                                operation="index_file",
                                target_type="document",
                                target_id=doc.doc_id,
                                result="success",
                                detail_json=build_file_audit_detail(
                                    scanned.path,
                                    chunk_count=len(chunks),
                                    hash=file_hash,
                                ),
                                trace_id=trace_id,
                            )
                        )
                        status = "success" if parsed.parse_status == "success" else "partial"
                        result = IndexedFileResult(
                            path=str(scanned.path),
                            doc_id=doc.doc_id,
                            status=status,
                            chunk_count=len(chunks),
                        )
        # ← session.commit() succeeded (all branches reach here)

        # === Phase B: audit.jsonl (after commit, all branches) ===
        for audit_record in audit_records:
            flush_audit_to_jsonl(audit_record)

        # === Phase C: HNSW (after commit, best-effort) ===
        if self._hnsw and (old_chunk_ids or new_chunk_ids):
            if new_chunk_ids and (
                self._embedder is None or not hasattr(self._embedder, "embed_batch")
            ):
                self._hnsw.mark_dirty()
                self._hnsw.mark_failed(
                    self._engine,
                    embedder=self._embedder,
                    reason="index_file_no_embedder",
                    last_error="embedder unavailable for dense update",
                )
                logger.warning("HNSW write skipped, embedder unavailable")
            else:
                try:
                    if old_chunk_ids:
                        self._hnsw.mark_deleted(old_chunk_ids)
                    if new_chunk_ids:
                        texts = [cr.text for cr in chunks] if chunks else []
                        vectors = self._embedder.embed_batch(texts)
                        self._hnsw.add_chunks_with_vectors(new_chunk_ids, vectors)
                    self._hnsw.mark_ready(
                        self._engine,
                        embedder=self._embedder,
                        reason="index_file_incremental",
                    )
                except Exception as exc:
                    self._hnsw.mark_dirty()
                    self._hnsw.mark_failed(
                        self._engine,
                        embedder=self._embedder,
                        reason="index_file_hnsw_update_failed",
                        last_error=str(exc),
                    )
                    logger.warning("HNSW write failed, marked dirty")

        assert result is not None
        return result

    def index_batch(
        self,
        files: list[ScannedFile],
        *,
        source_root_id: str,
        trace_id: str,
        force: bool = False,
    ) -> IndexBatchResult:
        """Index multiple files. Each file gets its own session (TC-002 isolation)."""
        start = time.monotonic()
        batch = IndexBatchResult(total=len(files))
        resolution_state: BatchResolutionState | None = None

        with session_scope(self._engine) as session:
            active_documents = DocumentRepository(session).list_active_by_source_root(
                source_root_id
            )
            resolution_state = BatchResolutionState.build(active_documents)

        for f in files:
            try:
                r = self.index_file(
                    f,
                    source_root_id=source_root_id,
                    trace_id=trace_id,
                    force=force,
                    resolution_state=resolution_state,
                )
                batch.results.append(r)
                if r.status == "success":
                    batch.success_count += 1
                elif r.status == "partial":
                    batch.partial_count += 1
                elif r.status == "failed":
                    batch.failed_count += 1
                elif r.status == "skipped":
                    batch.skipped_count += 1
            except Exception as exc:
                logger.exception("Unhandled error indexing %s", f.path)
                batch.results.append(
                    IndexedFileResult(
                        path=str(f.path),
                        doc_id="",
                        status="failed",
                        error_info=str(exc),
                    )
                )
                batch.failed_count += 1

        # HNSW compensation at end of batch
        if self._hnsw and self._hnsw.is_dirty():
            if self._embedder is None or not hasattr(self._embedder, "embed_batch"):
                batch.hnsw_status = "degraded"
                logger.warning("HNSW dirty but no embedder available for compensation rebuild")
            else:
                try:
                    self._hnsw.rebuild_from_db(
                        self._engine,
                        embedder=self._embedder,
                        reason="batch_compensation_dirty",
                    )
                except Exception:
                    batch.hnsw_status = "degraded"
                    logger.warning("HNSW rebuild failed, status=degraded")

        batch.duration_sec = time.monotonic() - start
        return batch

    def remove_document(
        self,
        doc_id: str,
        *,
        trace_id: str,
        soft_delete: bool = True,
        expected_path: str | None = None,
    ) -> bool:
        """Remove a document from the index (soft-delete + chunk cleanup)."""
        audit_record: AuditLogModel | None = None
        chunk_ids: list[str] = []

        with session_scope(self._engine) as session:
            doc_repo = DocumentRepository(session)
            chunk_repo = ChunkRepository(session)

            doc = doc_repo.get_by_id(doc_id)
            if doc is None:
                return False
            if expected_path is not None and doc.path != expected_path:
                return False

            # Collect chunk IDs before deleting
            chunks = chunk_repo.list_by_document(doc_id)
            chunk_ids = [c.chunk_id for c in chunks]

            if soft_delete:
                doc_repo.mark_deleted_from_fs(doc_id)
            if self._hnsw is not None and chunk_ids:
                self._hnsw.mark_stale(
                    session,
                    embedder=self._embedder,
                    reason="document_removed",
                )
            chunk_repo.delete_by_doc_id(doc_id, allow_delete=True)

            audit_record = create_audit_record(
                session,
                actor="system",
                operation="remove_document",
                target_type="document",
                target_id=doc_id,
                result="success",
                detail_json=build_file_audit_detail(doc.path, chunk_count=len(chunk_ids)),
                trace_id=trace_id,
            )

        if audit_record is not None:
            flush_audit_to_jsonl(audit_record)

        if self._hnsw and chunk_ids:
            try:
                self._hnsw.mark_deleted(chunk_ids)
                self._hnsw.mark_ready(
                    self._engine,
                    embedder=self._embedder,
                    reason="remove_document_incremental",
                )
            except Exception as exc:
                self._hnsw.mark_dirty()
                self._hnsw.mark_failed(
                    self._engine,
                    embedder=self._embedder,
                    reason="remove_document_hnsw_update_failed",
                    last_error=str(exc),
                )

        return True

    @staticmethod
    def _resolve_existing_document(
        doc_repo: DocumentRepository,
        scanned: ScannedFile,
        *,
        resolution_state: BatchResolutionState | None = None,
    ) -> DocumentResolution:
        if resolution_state is not None:
            return IndexBuilder._resolve_existing_document_from_batch(
                doc_repo,
                scanned,
                resolution_state,
            )

        identity_match = None
        if scanned.file_identity is not None:
            # file_identity belongs to the current active filesystem lineage only.
            # Historical deleted rows keep their provenance but must not be
            # resurrected implicitly when the filesystem later reuses the same
            # inode / identity.
            identity_match = doc_repo.get_by_file_identity(
                scanned.file_identity,
                include_deleted=False,
            )

        path_match = doc_repo.get_by_path(str(scanned.path))

        existing = identity_match
        if existing is None and path_match is not None:
            if scanned.file_identity is None or path_match.file_identity is None:
                existing = path_match

        displaced = None
        if path_match is not None and (existing is None or path_match.doc_id != existing.doc_id):
            displaced = path_match

        return DocumentResolution(existing=existing, displaced=displaced)

    @staticmethod
    def _resolve_existing_document_from_batch(
        doc_repo: DocumentRepository,
        scanned: ScannedFile,
        resolution_state: BatchResolutionState,
    ) -> DocumentResolution:
        """Resolve against the batch snapshot, not against already-mutated rows."""
        identity_snapshot = resolution_state.match_by_identity(scanned.file_identity)
        path_snapshot = resolution_state.match_by_path(str(scanned.path))

        existing_snapshot = identity_snapshot
        if existing_snapshot is None and path_snapshot is not None:
            if scanned.file_identity is None or path_snapshot.file_identity is None:
                existing_snapshot = path_snapshot

        existing = None
        if existing_snapshot is not None:
            existing = doc_repo.get_by_id(existing_snapshot.doc_id)

        displaced = None
        if path_snapshot is not None and (
            existing_snapshot is None or path_snapshot.doc_id != existing_snapshot.doc_id
        ):
            displaced = doc_repo.get_by_id(path_snapshot.doc_id)

        return DocumentResolution(existing=existing, displaced=displaced)

    @staticmethod
    def _retire_displaced_document(
        session: object,
        doc_repo: DocumentRepository,
        chunk_repo: ChunkRepository,
        *,
        displaced: DocumentModel | None,
        replacement_path: str,
        trace_id: str,
        audit_records: list[AuditLogModel],
    ) -> list[str]:
        if displaced is None:
            return []

        chunk_ids = [chunk.chunk_id for chunk in chunk_repo.list_by_document(displaced.doc_id)]
        if chunk_ids:
            chunk_repo.delete_by_doc_id(displaced.doc_id, allow_delete=True)
        doc_repo.mark_deleted_from_fs(displaced.doc_id)
        audit_records.append(
            create_audit_record(
                session,
                actor="system",
                operation="remove_document",
                target_type="document",
                target_id=displaced.doc_id,
                result="success",
                detail_json=build_file_audit_detail(
                    displaced.path,
                    chunk_count=len(chunk_ids),
                    replacement_path=replacement_path,
                    reason="path_reused_by_different_document",
                ),
                trace_id=trace_id,
            )
        )
        return chunk_ids

    @staticmethod
    def _can_skip_existing(
        existing: DocumentModel | None,
        chunk_repo: ChunkRepository,
        *,
        scanned: ScannedFile,
        file_hash: str,
        source_config_rev: int,
        force: bool,
    ) -> bool:
        if force or existing is None:
            return False
        if existing.path != str(scanned.path):
            return False
        if scanned.file_identity is not None and existing.file_identity is None:
            return False
        if existing.file_identity is not None and existing.file_identity != scanned.file_identity:
            return False
        if existing.hash_sha256 != file_hash:
            return False
        if existing.parse_status not in {"success", "partial"}:
            return False
        if existing.is_deleted_from_fs:
            return False
        if existing.source_config_rev != source_config_rev:
            return False
        return len(chunk_repo.list_by_document(existing.doc_id)) > 0

    @staticmethod
    def _upsert_document(
        existing: DocumentModel | None,
        doc_repo: DocumentRepository,
        scanned: ScannedFile,
        file_hash: str | None,
        parsed: ParsedDocument,
        metadata: DocumentMetadata,
        source: SourceRootModel,
        doc_id: str,
    ) -> DocumentModel:
        directory_path, relative_directory_path = derive_directory_facts(
            str(scanned.path),
            scanned.relative_path,
        )
        display_path = build_display_path(source.display_root, scanned.relative_path)
        if existing:
            existing.path = str(scanned.path)
            existing.hash_sha256 = file_hash
            existing.relative_path = scanned.relative_path
            existing.display_path = display_path
            existing.file_identity = scanned.file_identity
            existing.source_root_id = source.source_root_id
            existing.source_config_rev = source.source_config_rev
            existing.title = parsed.title or scanned.path.stem
            existing.file_type = scanned.file_type
            existing.size_bytes = scanned.size_bytes
            existing.created_at = scanned.created_at
            existing.modified_at = scanned.modified_at
            existing.parse_status = parsed.parse_status
            existing.directory_path = directory_path
            existing.relative_directory_path = relative_directory_path
            existing.category = metadata.category
            existing.tags_json = list(metadata.tags)
            existing.sensitivity = metadata.sensitivity or "internal"
            existing.is_deleted_from_fs = False
            if parsed.parse_status == "failed":
                existing.indexed_at = None
            return existing

        doc = DocumentModel(
            doc_id=doc_id,
            path=str(scanned.path),
            relative_path=scanned.relative_path,
            display_path=display_path,
            directory_path=directory_path,
            relative_directory_path=relative_directory_path,
            file_identity=scanned.file_identity,
            source_root_id=source.source_root_id,
            source_config_rev=source.source_config_rev,
            source_path=str(scanned.path),
            hash_sha256=file_hash,
            title=parsed.title or scanned.path.stem,
            file_type=scanned.file_type,
            size_bytes=scanned.size_bytes,
            created_at=scanned.created_at,
            modified_at=scanned.modified_at,
            parse_status=parsed.parse_status,
            category=metadata.category,
            tags_json=list(metadata.tags),
            sensitivity=metadata.sensitivity or "internal",
        )
        doc_repo.create(doc)
        return doc

    @staticmethod
    def _require_source_root(session: object, source_root_id: str) -> SourceRootModel:
        source = session.get(SourceRootModel, source_root_id)
        if source is None:
            raise ValueError(f"source root not found during indexing: {source_root_id}")
        return source

    @staticmethod
    def _source_defaults(source: SourceRootModel) -> DocumentMetadata:
        return DocumentMetadata(
            category=source.default_category,
            tags=source.default_tags_json,
            sensitivity=source.default_sensitivity,
        )
