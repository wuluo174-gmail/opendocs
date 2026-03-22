"""S6-T03/T04: Archive service — classify, plan, execute, rollback."""

from __future__ import annotations

import hashlib
import os
import shutil
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from opendocs.app._audit_helpers import create_audit_record, flush_audit_to_jsonl
from opendocs.app.file_operation_service import FileOperationService
from opendocs.audit.rollback import build_rollback_audit_detail
from opendocs.classification.classifier import RuleBasedClassifier
from opendocs.classification.models import PlannedMove, RollbackItem
from opendocs.classification.path_planner import PathPlanner
from opendocs.domain.models import DocumentModel, FileOperationPlanModel
from opendocs.exceptions import (
    FileOpFailedError,
    OpenDocsError,
    RollbackPartialError,
)
from opendocs.storage.db import session_scope
from opendocs.storage.repositories import AuditRepository, PlanRepository
from opendocs.utils.time import utcnow_naive


class ArchiveService:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def classify_and_plan(
        self,
        doc_ids: list[str],
        *,
        base_archive_dir: str,
        trace_id: str | None = None,
    ) -> str:
        """Classify documents and create a draft archive plan. Zero file writes."""
        trace_id = trace_id or str(uuid.uuid4())

        with session_scope(self._engine) as session:
            docs = self._load_docs(session, doc_ids)
            classifications = RuleBasedClassifier().classify(docs)
            hashes = {d.doc_id: d.hash_sha256 for d in docs}
            planned = PathPlanner(base_archive_dir).plan(classifications, hashes=hashes)

            has_conflict = any(p.conflict for p in planned)
            plan = FileOperationPlanModel(
                plan_id=str(uuid.uuid4()),
                operation_type="move",
                status="draft",
                item_count=len(planned),
                risk_level="high" if has_conflict else "low",
                preview_json=self._build_preview(planned),
            )
            PlanRepository(session).create(plan)

            audit = create_audit_record(
                session,
                actor="system",
                operation="archive_plan",
                target_type="plan",
                target_id=plan.plan_id,
                result="success",
                detail_json={"item_count": len(planned), "has_conflict": has_conflict},
                trace_id=trace_id,
            )

        flush_audit_to_jsonl(audit)
        return plan.plan_id

    def get_plan(self, plan_id: str) -> FileOperationPlanModel:
        with session_scope(self._engine) as session:
            plan = PlanRepository(session).get_by_id(plan_id)
            if plan is None:
                raise OpenDocsError(f"plan not found: {plan_id}")
            return plan

    def approve(self, plan_id: str) -> FileOperationPlanModel:
        with session_scope(self._engine) as session:
            svc = FileOperationService(session)
            return svc.approve_plan(plan_id)

    def execute(
        self, plan_id: str, *, trace_id: str | None = None
    ) -> FileOperationPlanModel:
        trace_id = trace_id or str(uuid.uuid4())

        with session_scope(self._engine) as session:
            svc = FileOperationService(
                session,
                operation_executor=self._make_executor(session),
            )
            plan, _audit = svc.execute_plan(
                plan_id,
                actor="user",
                trace_id=trace_id,
            )
            return plan

    def rollback_last_batch(
        self, *, trace_id: str | None = None
    ) -> list[RollbackItem]:
        trace_id = trace_id or str(uuid.uuid4())

        with session_scope(self._engine) as session:
            plan_repo = PlanRepository(session)
            plan = plan_repo.get_latest_by_status("executed")
            if plan is None:
                raise OpenDocsError("no executed plan to rollback")

            items = self._do_rollback(plan)
            failed = [i for i in items if not i.restored]

            if failed:
                plan.status = "failed"
            else:
                plan.status = "rolled_back"
            session.flush()

            audit = create_audit_record(
                session,
                actor="user",
                operation="rollback_execute",
                target_type="rollback",
                target_id=plan.plan_id,
                result="failure" if failed else "success",
                detail_json=build_rollback_audit_detail(plan.plan_id, items),
                trace_id=trace_id,
            )

        flush_audit_to_jsonl(audit)

        if failed:
            raise RollbackPartialError(
                f"{len(failed)} file(s) could not be restored"
            )
        return items

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_docs(
        self, session: Session, doc_ids: list[str]
    ) -> list[DocumentModel]:
        stmt = select(DocumentModel).where(DocumentModel.doc_id.in_(doc_ids))
        docs = list(session.scalars(stmt))
        if len(docs) != len(doc_ids):
            found = {d.doc_id for d in docs}
            missing = set(doc_ids) - found
            raise OpenDocsError(f"documents not found: {missing}")
        return docs

    def _build_preview(self, planned: list[PlannedMove]) -> dict[str, Any]:
        return {
            "items": [p.model_dump() for p in planned],
            "classification_trace": {
                "strategy": "rule_based",
                "timestamp": utcnow_naive().isoformat(),
            },
        }

    def _make_executor(self, session: Session):
        def executor(plan: FileOperationPlanModel) -> None:
            items = plan.preview_json.get("items", [])
            completed: list[dict[str, str]] = []

            for item in items:
                if item.get("conflict"):
                    self._rollback_completed(completed)
                    raise FileOpFailedError(
                        f"conflict: target already exists: {item['target_path']}"
                    )

                src = item["source_path"]
                tgt = item["target_path"]

                if not os.path.exists(src):
                    self._rollback_completed(completed)
                    raise FileOpFailedError(f"source file missing: {src}")

                if os.path.exists(tgt):
                    self._rollback_completed(completed)
                    raise FileOpFailedError(
                        f"target already exists at execution time: {tgt}"
                    )

                if item.get("hash_sha256"):
                    actual = _file_sha256(src)
                    if actual != item["hash_sha256"]:
                        self._rollback_completed(completed)
                        raise FileOpFailedError(
                            f"hash mismatch for {src}: expected {item['hash_sha256']}, got {actual}"
                        )

                os.makedirs(os.path.dirname(tgt), exist_ok=True)
                shutil.move(src, tgt)
                completed.append({"source": src, "target": tgt})

        return executor

    def _rollback_completed(self, completed: list[dict[str, str]]) -> None:
        for entry in reversed(completed):
            try:
                shutil.move(entry["target"], entry["source"])
            except OSError:
                pass

    def _do_rollback(self, plan: FileOperationPlanModel) -> list[RollbackItem]:
        items_data = plan.preview_json.get("items", [])
        results: list[RollbackItem] = []

        for item in items_data:
            src = item["source_path"]
            tgt = item["target_path"]
            doc_id = item["doc_id"]

            try:
                if not os.path.exists(tgt):
                    results.append(RollbackItem(
                        doc_id=doc_id,
                        original_path=src,
                        current_path=tgt,
                        restored=False,
                        error=f"file not found at target: {tgt}",
                    ))
                    continue

                os.makedirs(os.path.dirname(src), exist_ok=True)
                shutil.move(tgt, src)
                results.append(RollbackItem(
                    doc_id=doc_id,
                    original_path=src,
                    current_path=src,
                    restored=True,
                ))
            except OSError as exc:
                results.append(RollbackItem(
                    doc_id=doc_id,
                    original_path=src,
                    current_path=tgt,
                    restored=False,
                    error=str(exc),
                ))

        return results


def _file_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()
