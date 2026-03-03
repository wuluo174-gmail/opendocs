"""Seed demo records for S1 storage baseline."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path
import uuid

from opendocs.domain.models import AuditLogModel, ChunkModel, DocumentModel, FileOperationPlanModel, MemoryItemModel
from opendocs.storage.db import build_sqlite_engine, init_db, session_scope
from opendocs.storage.repositories import (
    AuditRepository,
    ChunkRepository,
    DocumentRepository,
    MemoryRepository,
    PlanRepository,
)

DOC_ID = "00000000-0000-0000-0000-000000000101"
CHUNK_ID = "00000000-0000-0000-0000-000000000201"
MEMORY_ID = "00000000-0000-0000-0000-000000000301"
PLAN_ID = "00000000-0000-0000-0000-000000000401"
AUDIT_ID = "00000000-0000-0000-0000-000000000501"
DEMO_DOC_PATH = "C:/opendocs/demo/project_overview.md"
DEMO_DOC_RELATIVE_PATH = "demo/project_overview.md"
DEMO_CHUNK_INDEX = 0
DEMO_MEMORY_SCOPE_ID = "demo-task"
DEMO_MEMORY_KEY = "owner"


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _preferred_or_new_id(preferred_id: str, exists: bool) -> str:
    if not exists:
        return preferred_id
    return str(uuid.uuid4())


def seed_demo_data(db_path: str | Path) -> dict[str, int]:
    init_db(db_path)
    engine = build_sqlite_engine(db_path)
    inserted = {
        "documents": 0,
        "chunks": 0,
        "memory_items": 0,
        "file_operation_plans": 0,
        "audit_logs": 0,
    }

    try:
        with session_scope(engine) as session:
            document_repo = DocumentRepository(session)
            chunk_repo = ChunkRepository(session)
            memory_repo = MemoryRepository(session)
            plan_repo = PlanRepository(session)
            audit_repo = AuditRepository(session)

            now = _now()
            document = document_repo.get_by_path(DEMO_DOC_PATH)
            if document is None:
                document_id = _preferred_or_new_id(DOC_ID, document_repo.get_by_id(DOC_ID) is not None)
                document_repo.create(
                    DocumentModel(
                        doc_id=document_id,
                        path=DEMO_DOC_PATH,
                        relative_path=DEMO_DOC_RELATIVE_PATH,
                        source_root_id="00000000-0000-0000-0000-000000000001",
                        source_path=DEMO_DOC_PATH,
                        hash_sha256="c" * 64,
                        title="Project Overview",
                        file_type="md",
                        size_bytes=2048,
                        created_at=now,
                        modified_at=now,
                        indexed_at=now,
                        parse_status="success",
                        category="project",
                        tags_json=["demo", "overview"],
                        sensitivity="internal",
                        is_deleted_from_fs=False,
                    )
                )
                inserted["documents"] += 1
                document = document_repo.get_by_id(document_id)

            if document is None:
                raise RuntimeError("failed to resolve demo document")

            chunk = chunk_repo.get_by_document_index(document.doc_id, DEMO_CHUNK_INDEX)
            if chunk is None:
                chunk_id = _preferred_or_new_id(CHUNK_ID, chunk_repo.get_by_id(CHUNK_ID) is not None)
                demo_chunk_text = "OpenDocs demo chunk text for retrieval and audit tracing."
                chunk_repo.create(
                    ChunkModel(
                        chunk_id=chunk_id,
                        doc_id=document.doc_id,
                        chunk_index=DEMO_CHUNK_INDEX,
                        text=demo_chunk_text,
                        char_start=0,
                        char_end=len(demo_chunk_text),
                        page_no=None,
                        paragraph_start=1,
                        paragraph_end=1,
                        heading_path="Overview",
                        token_estimate=16,
                        embedding_model="demo-embedding-model",
                        embedding_key="chunk-demo-0001",
                    )
                )
                inserted["chunks"] += 1
                chunk = chunk_repo.get_by_id(chunk_id)

            if chunk is None:
                raise RuntimeError("failed to resolve demo chunk")

            memory = memory_repo.get_by_scope_key(
                memory_type="M1",
                scope_type="task",
                scope_id=DEMO_MEMORY_SCOPE_ID,
                key=DEMO_MEMORY_KEY,
            )
            if memory is None:
                memory_id = _preferred_or_new_id(
                    MEMORY_ID,
                    memory_repo.get_by_id(MEMORY_ID) is not None,
                )
                memory_repo.create(
                    MemoryItemModel(
                        memory_id=memory_id,
                        memory_type="M1",
                        scope_type="task",
                        scope_id=DEMO_MEMORY_SCOPE_ID,
                        key=DEMO_MEMORY_KEY,
                        content="Alice",
                        importance=0.8,
                        status="active",
                        ttl_days=30,
                        confirmed_count=1,
                        last_confirmed_at=now,
                        updated_at=now,
                    )
                )
                inserted["memory_items"] += 1

            if plan_repo.get_by_id(PLAN_ID) is None:
                plan_repo.create(
                    FileOperationPlanModel(
                        plan_id=PLAN_ID,
                        operation_type="move",
                        status="draft",
                        item_count=1,
                        risk_level="low",
                        preview_json={
                            "items": [
                                {
                                    "source": "C:/opendocs/demo/project_overview.md",
                                    "target": "C:/opendocs/archive/project_overview.md",
                                }
                            ]
                        },
                    )
                )
                inserted["file_operation_plans"] += 1

            if audit_repo.get_by_id(AUDIT_ID) is None:
                audit_repo.create(
                    AuditLogModel(
                        audit_id=AUDIT_ID,
                        timestamp=now,
                        actor="system",
                        operation="seed_demo_data",
                        target_type="document",
                        target_id=document.doc_id,
                        result="success",
                        detail_json={
                            "file_path": DEMO_DOC_PATH,
                            "chunk_id": chunk.chunk_id,
                            "note": "seed for S1 tests",
                        },
                        trace_id="trace-seed-001",
                    )
                )
                inserted["audit_logs"] += 1
    finally:
        engine.dispose()

    return inserted


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Seed OpenDocs demo data")
    parser.add_argument(
        "--db-path",
        required=True,
        type=Path,
        help="SQLite database path",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    inserted = seed_demo_data(args.db_path)
    print(f"seed completed for {args.db_path}: {inserted}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
