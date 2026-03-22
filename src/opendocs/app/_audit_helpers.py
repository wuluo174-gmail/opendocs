"""Two-phase audit helpers: DB record in txn, JSONL after commit."""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from opendocs.domain.models import AuditLogModel
from opendocs.storage.repositories import AuditRepository
from opendocs.utils.time import utcnow_naive

_audit_logger = logging.getLogger("opendocs.audit")
_app_logger = logging.getLogger("opendocs")


def normalize_audit_path(path: str | Path) -> str:
    """Return a canonical absolute path for audit payloads and lookups."""
    return str(Path(path).resolve())


def build_file_audit_detail(
    path: str | Path,
    **detail: object,
) -> dict[str, Any]:
    """Build a canonical file-audit payload.

    Canonical key for file-scoped audit payloads is ``file_path``.
    """
    normalized = normalize_audit_path(path)
    payload: dict[str, Any] = {
        "file_path": normalized,
    }
    payload.update(detail)
    return payload


def build_text_input_audit_detail(
    text: str,
    *,
    field_name: str,
    **detail: object,
) -> dict[str, Any]:
    normalized = text.strip()
    payload: dict[str, Any] = {
        f"{field_name}_sha256": hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
        f"{field_name}_length": len(normalized),
    }
    payload.update(detail)
    return payload


def create_audit_record(
    session: Session,
    *,
    actor: str,
    operation: str,
    target_type: str,
    target_id: str,
    result: str,
    detail_json: dict[str, object] | None = None,
    trace_id: str,
    timestamp: datetime | None = None,
    audit_id: str | None = None,
) -> AuditLogModel:
    """Phase A: write DB audit record inside session_scope (rolls back with txn)."""
    ts = timestamp or utcnow_naive()
    audit = AuditLogModel(
        audit_id=audit_id or str(uuid.uuid4()),
        timestamp=ts,
        actor=actor,
        operation=operation,
        target_type=target_type,
        target_id=target_id,
        result=result,
        detail_json=detail_json or {},
        trace_id=trace_id,
    )
    AuditRepository(session).create(audit)
    return audit


def flush_audit_to_jsonl(audit: AuditLogModel) -> None:
    """Phase B: write to audit.jsonl AFTER session commit succeeds.

    Must be called outside session_scope. I/O failures are caught and
    logged as warnings (never block business logic).
    """
    try:
        _audit_logger.info(
            "audit_event",
            extra={
                "audit_data": {
                    "audit_id": audit.audit_id,
                    "timestamp": audit.timestamp.isoformat() if audit.timestamp else "",
                    "actor": audit.actor,
                    "operation": audit.operation,
                    "target_type": audit.target_type,
                    "target_id": audit.target_id,
                    "result": audit.result,
                    "detail": audit.detail_json,
                    "trace_id": audit.trace_id,
                }
            },
        )
    except Exception:
        _app_logger.warning("audit.jsonl write failed for audit_id=%s", audit.audit_id)
