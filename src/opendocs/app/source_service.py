"""Application service for source root management (S3-T01)."""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.engine import Engine

from opendocs.app._audit_helpers import create_audit_record, flush_audit_to_jsonl
from opendocs.domain.document_metadata import DocumentMetadata
from opendocs.domain.models import (
    AuditLogModel,
    IndexArtifactModel,
    ScanRunModel,
    SourceRootModel,
)
from opendocs.exceptions import OpenDocsError, SourceNotFoundError, SourceOverlapError
from opendocs.indexing.scanner import ExcludeRules, Scanner, ScanResult
from opendocs.parsers import create_default_registry
from opendocs.storage.db import session_scope
from opendocs.storage.repositories import ScanRunRepository, SourceRepository
from opendocs.storage.repositories.source_repository import INDEX_RELEVANT_SOURCE_FIELDS
from opendocs.utils.path_facts import derive_source_display_root
from opendocs.utils.time import utcnow_naive

_UNSET = object()


@dataclass(frozen=True)
class _ScanRequest:
    source_root_id: str
    source_root_path: str
    recursive: bool
    rules: ExcludeRules
    trace_id: str


@dataclass(frozen=True)
class _SourceUpdatePlan:
    updates: dict[str, object]
    requires_reindex: bool


class SourceService:
    """Manage document source roots and scanning."""

    def __init__(self, engine: Engine, *, hnsw_path: Path | None = None) -> None:
        self._engine = engine
        self._hnsw_path = hnsw_path
        self._scanner = Scanner(create_default_registry())

    def add_source(
        self,
        path: str | Path,
        *,
        label: str | None | object = _UNSET,
        exclude_rules: ExcludeRules | dict[str, object] | None | object = _UNSET,
        default_metadata: DocumentMetadata | dict[str, object] | None | object = _UNSET,
        recursive: bool | object = _UNSET,
        reindex_on_change: bool = True,
    ) -> SourceRootModel:
        """Add a source root. Existing paths are updated in place."""
        resolved = self._require_readable_directory(path)

        audit_record: AuditLogModel | None = None
        reindex_source_id: str | None = None
        source: SourceRootModel

        with session_scope(self._engine) as session:
            repo = SourceRepository(session)
            existing = repo.get_by_path(str(resolved))
            if existing:
                update_plan = self._plan_source_update(
                    existing,
                    self._build_source_updates(
                        label,
                        exclude_rules,
                        default_metadata,
                        recursive,
                    ),
                )
                changed = (
                    repo.update(existing, **update_plan.updates) if update_plan.updates else False
                )
                source = existing
                if changed:
                    if update_plan.requires_reindex:
                        reindex_source_id = source.source_root_id
                    audit_record = create_audit_record(
                        session,
                        actor="system",
                        operation="update_source",
                        target_type="source",
                        target_id=source.source_root_id,
                        result="success",
                        detail_json={"path": str(resolved), "label": source.label},
                        trace_id=str(uuid.uuid4()),
                    )
            else:
                self._ensure_disjoint_active_source_roots(repo, resolved)
                rules = self._coerce_exclude_rules(exclude_rules)
                defaults = self._coerce_default_metadata(default_metadata)
                source_root_id = str(uuid.uuid4())
                source = SourceRootModel(
                    source_root_id=source_root_id,
                    path=str(resolved),
                    display_root=self._allocate_display_root(
                        repo,
                        path=str(resolved),
                        source_root_id=source_root_id,
                    ),
                    label=None if label is _UNSET else label,
                    exclude_rules_json=rules.model_dump(),  # type: ignore[assignment]
                    default_category=defaults.category,
                    default_tags_json=list(defaults.tags),
                    default_sensitivity=defaults.sensitivity,
                    recursive=True if recursive is _UNSET else recursive,
                )
                repo.create(source)

                audit_record = create_audit_record(
                    session,
                    actor="system",
                    operation="add_source",
                    target_type="source",
                    target_id=source.source_root_id,
                    result="success",
                    detail_json={"path": str(resolved), "label": source.label},
                    trace_id=str(uuid.uuid4()),
                )

        if audit_record is not None:
            flush_audit_to_jsonl(audit_record)
        if reindex_source_id is not None and reindex_on_change:
            self._trigger_reindex(reindex_source_id)

        return source

    def update_source(
        self,
        source_root_id: str,
        *,
        label: str | None | object = _UNSET,
        exclude_rules: ExcludeRules | dict[str, object] | None | object = _UNSET,
        default_metadata: DocumentMetadata | dict[str, object] | None | object = _UNSET,
        recursive: bool | object = _UNSET,
        reindex_on_change: bool = True,
    ) -> SourceRootModel:
        """Update an existing source root configuration."""
        audit_record: AuditLogModel | None = None
        reindex_source_id: str | None = None
        with session_scope(self._engine) as session:
            repo = SourceRepository(session)
            source = repo.get_by_id(source_root_id)
            if source is None:
                raise SourceNotFoundError(f"source root not found: {source_root_id}")

            self._require_readable_directory(source.path)
            update_plan = self._plan_source_update(
                source,
                self._build_source_updates(
                    label,
                    exclude_rules,
                    default_metadata,
                    recursive,
                ),
            )
            changed = repo.update(source, **update_plan.updates) if update_plan.updates else False
            if changed:
                if update_plan.requires_reindex:
                    reindex_source_id = source.source_root_id
                audit_record = create_audit_record(
                    session,
                    actor="system",
                    operation="update_source",
                    target_type="source",
                    target_id=source.source_root_id,
                    result="success",
                    detail_json={"path": source.path, "label": source.label},
                    trace_id=str(uuid.uuid4()),
                )

        if audit_record is not None:
            flush_audit_to_jsonl(audit_record)
        if reindex_source_id is not None and reindex_on_change:
            self._trigger_reindex(reindex_source_id)

        return source

    def update_source_by_path(
        self,
        path: str | Path,
        *,
        label: str | None | object = _UNSET,
        exclude_rules: ExcludeRules | dict[str, object] | None | object = _UNSET,
        default_metadata: DocumentMetadata | dict[str, object] | None | object = _UNSET,
        recursive: bool | object = _UNSET,
        reindex_on_change: bool = True,
    ) -> SourceRootModel:
        """Update an existing source root using the user-owned source path."""
        source = self.get_source_by_path(path)
        if source is None:
            resolved = self._resolve_source_path(path)
            raise SourceNotFoundError(f"source root not found for path: {resolved}")
        return self.update_source(
            source.source_root_id,
            label=label,
            exclude_rules=exclude_rules,
            default_metadata=default_metadata,
            recursive=recursive,
            reindex_on_change=reindex_on_change,
        )

    @staticmethod
    def _resolve_source_path(path: str | Path) -> Path:
        return Path(path).expanduser().resolve()

    @staticmethod
    def _require_readable_directory(path: str | Path) -> Path:
        resolved = SourceService._resolve_source_path(path)
        if not resolved.exists() or not resolved.is_dir():
            raise SourceNotFoundError(f"path does not exist or is not a directory: {resolved}")
        if not os.access(resolved, os.R_OK | os.X_OK):
            raise SourceNotFoundError(f"path is not readable: {resolved}")
        try:
            with os.scandir(resolved) as entries:
                next(entries, None)
        except PermissionError as exc:
            raise SourceNotFoundError(f"path is not readable: {resolved}") from exc
        except OSError as exc:
            raise SourceNotFoundError(f"path is not readable: {resolved}") from exc
        return resolved

    @staticmethod
    def _ensure_disjoint_active_source_roots(
        repo: SourceRepository,
        candidate_path: Path,
    ) -> None:
        candidate = candidate_path.resolve()
        for source in repo.list_active():
            existing = Path(source.path).resolve()
            if existing == candidate:
                continue
            if candidate.is_relative_to(existing) or existing.is_relative_to(candidate):
                raise SourceOverlapError(
                    "source root ownership must be disjoint; "
                    f"{candidate} overlaps active source root {existing}"
                )

    @staticmethod
    def _coerce_exclude_rules(
        exclude_rules: ExcludeRules | dict[str, object] | None | object,
    ) -> ExcludeRules:
        if exclude_rules is _UNSET or exclude_rules is None:
            return ExcludeRules()
        return ExcludeRules.model_validate(exclude_rules)

    @staticmethod
    def _coerce_default_metadata(
        default_metadata: DocumentMetadata | dict[str, object] | None | object,
    ) -> DocumentMetadata:
        if default_metadata is _UNSET or default_metadata is None:
            return DocumentMetadata()
        if isinstance(default_metadata, DocumentMetadata):
            return default_metadata
        return DocumentMetadata.model_validate(default_metadata)

    def _build_source_updates(
        self,
        label: str | None | object,
        exclude_rules: ExcludeRules | dict[str, object] | None | object,
        default_metadata: DocumentMetadata | dict[str, object] | None | object,
        recursive: bool | object,
    ) -> dict[str, object]:
        updates: dict[str, object] = {}
        if label is not _UNSET:
            updates["label"] = label
        if exclude_rules is not _UNSET:
            updates["exclude_rules_json"] = self._coerce_exclude_rules(exclude_rules).model_dump()
        if default_metadata is not _UNSET:
            updates.update(self._coerce_default_metadata(default_metadata).to_source_defaults())
        if recursive is not _UNSET:
            updates["recursive"] = recursive
        return updates

    @staticmethod
    def _allocate_display_root(
        repo: SourceRepository,
        *,
        path: str,
        source_root_id: str,
    ) -> str:
        occupied = {source.display_root for source in repo.list_all()}
        return derive_source_display_root(
            path,
            source_root_id=source_root_id,
            occupied_roots=occupied,
        )

    @staticmethod
    def _plan_source_update(
        source: SourceRootModel,
        requested_updates: dict[str, object],
    ) -> _SourceUpdatePlan:
        effective_updates: dict[str, object] = {}
        requires_reindex = False
        for field, value in requested_updates.items():
            if getattr(source, field) == value:
                continue
            effective_updates[field] = value
            if field in INDEX_RELEVANT_SOURCE_FIELDS:
                requires_reindex = True
        return _SourceUpdatePlan(
            updates=effective_updates,
            requires_reindex=requires_reindex,
        )

    def _trigger_reindex(self, source_root_id: str) -> None:
        from opendocs.app.index_service import IndexService

        resolved_hnsw_path = self._resolve_hnsw_path()
        IndexService(
            self._engine,
            hnsw_path=resolved_hnsw_path,
        ).update_index_for_changes(source_root_id)

    def _resolve_hnsw_path(self) -> Path | None:
        if self._hnsw_path is not None:
            return self._hnsw_path
        with session_scope(self._engine) as session:
            artifact = session.get(IndexArtifactModel, "dense_hnsw")
            if artifact is None or not artifact.artifact_path:
                return None
            return Path(artifact.artifact_path)

    def scan_source(self, source_root_id: str) -> tuple[ScanResult, ScanRunModel]:
        """Scan a source root. Returns (ScanResult, ScanRunModel) for TC-001."""
        request = self._load_scan_request(source_root_id)
        scan_run = self._create_running_scan_run(request)

        try:
            scan_result = self._scanner.scan(
                Path(request.source_root_path),
                source_root_id=request.source_root_id,
                exclude_rules=request.rules,
                recursive=request.recursive,
            )
            if scan_result.has_root_failure:
                raise self._root_failure_to_exception(scan_result)
        except Exception as exc:
            failed_run, failure_audit = self._persist_scan_failure(
                request=request,
                scan_run_id=scan_run.scan_run_id,
                error=exc,
            )
            flush_audit_to_jsonl(failure_audit)
            raise

        completed_run, success_audit = self._persist_scan_success(
            request=request,
            scan_run_id=scan_run.scan_run_id,
            scan_result=scan_result,
        )
        flush_audit_to_jsonl(success_audit)
        return scan_result, completed_run

    def _load_scan_request(self, source_root_id: str) -> _ScanRequest:
        trace_id = str(uuid.uuid4())
        with session_scope(self._engine) as session:
            source = SourceRepository(session).get_by_id(source_root_id)
            if source is None:
                raise SourceNotFoundError(f"source root not found: {source_root_id}")
            return _ScanRequest(
                source_root_id=source_root_id,
                source_root_path=source.path,
                recursive=source.recursive,
                rules=ExcludeRules.model_validate(source.exclude_rules_json or {}),
                trace_id=trace_id,
            )

    def _create_running_scan_run(self, request: _ScanRequest) -> ScanRunModel:
        with session_scope(self._engine) as session:
            scan_run = ScanRunModel(
                scan_run_id=str(uuid.uuid4()),
                source_root_id=request.source_root_id,
                started_at=utcnow_naive(),
                trace_id=request.trace_id,
            )
            ScanRunRepository(session).create(scan_run)
            return scan_run

    def _persist_scan_success(
        self,
        *,
        request: _ScanRequest,
        scan_run_id: str,
        scan_result: ScanResult,
    ) -> tuple[ScanRunModel, AuditLogModel]:
        with session_scope(self._engine) as session:
            run_repo = ScanRunRepository(session)
            run = self._require_scan_run(run_repo, scan_run_id)
            run_repo.update_status(
                run,
                status="completed",
                included_count=scan_result.included_count,
                excluded_count=scan_result.excluded_count,
                unsupported_count=scan_result.unsupported_count,
                failed_count=scan_result.error_count,
                error_summary=self._scan_result_error_summary(scan_result),
            )
            audit_record = create_audit_record(
                session,
                actor="system",
                operation="scan_source",
                target_type="index_run",
                target_id=run.scan_run_id,
                result="success",
                detail_json={
                    "source_root_id": request.source_root_id,
                    "source_root_path": request.source_root_path,
                    "included_count": scan_result.included_count,
                    "excluded_count": scan_result.excluded_count,
                    "unsupported_count": scan_result.unsupported_count,
                    "error_count": scan_result.error_count,
                    "duration_sec": scan_result.duration_sec,
                },
                trace_id=request.trace_id,
            )
            return run, audit_record

    def _persist_scan_failure(
        self,
        *,
        request: _ScanRequest,
        scan_run_id: str,
        error: Exception,
    ) -> tuple[ScanRunModel, AuditLogModel]:
        failed_at = utcnow_naive()
        error_text = self._format_scan_error(error)
        error_summary = [{"path": request.source_root_path, "error": error_text}]

        with session_scope(self._engine) as session:
            run_repo = ScanRunRepository(session)
            run = self._require_scan_run(run_repo, scan_run_id)
            run_repo.update_status(
                run,
                status="failed",
                failed_count=len(error_summary),
                error_summary=error_summary,
                finished_at=failed_at,
            )
            audit_record = create_audit_record(
                session,
                actor="system",
                operation="scan_source",
                target_type="index_run",
                target_id=run.scan_run_id,
                result="failure",
                detail_json={
                    "source_root_id": request.source_root_id,
                    "source_root_path": request.source_root_path,
                    "included_count": 0,
                    "excluded_count": 0,
                    "unsupported_count": 0,
                    "error_count": len(error_summary),
                    "error_summary": error_summary,
                    "error_type": type(error).__name__,
                },
                trace_id=request.trace_id,
                timestamp=failed_at,
            )
            return run, audit_record

    @staticmethod
    def _require_scan_run(run_repo: ScanRunRepository, scan_run_id: str) -> ScanRunModel:
        run = run_repo.get_by_id(scan_run_id)
        if run is None:
            raise OpenDocsError(f"scan run not found after creation: {scan_run_id}")
        return run

    @staticmethod
    def _scan_result_error_summary(scan_result: ScanResult) -> list[dict[str, str]]:
        return [{"path": path, "error": error} for path, error in scan_result.errors]

    @staticmethod
    def _format_scan_error(error: Exception) -> str:
        message = str(error).strip()
        if not message:
            return type(error).__name__
        return f"{type(error).__name__}: {message}"

    @staticmethod
    def _root_failure_to_exception(scan_result: ScanResult) -> SourceNotFoundError:
        if scan_result.root_error is None:
            raise OpenDocsError("root failure exception requested without root_error")
        path, error = scan_result.root_error
        return SourceNotFoundError(f"source root scan failed: {path}: {error}")

    def list_sources(self) -> list[SourceRootModel]:
        with session_scope(self._engine) as session:
            return SourceRepository(session).list_active()

    def get_source(self, source_root_id: str) -> SourceRootModel | None:
        with session_scope(self._engine) as session:
            return SourceRepository(session).get_by_id(source_root_id)

    def get_source_by_path(self, path: str | Path) -> SourceRootModel | None:
        resolved = self._resolve_source_path(path)
        with session_scope(self._engine) as session:
            return SourceRepository(session).get_by_path(str(resolved))
