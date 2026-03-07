"""Tests for demo data seeding script."""

from __future__ import annotations

import importlib.util
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from opendocs.domain.models import (
    AuditLogModel,
    ChunkModel,
    DocumentModel,
    FileOperationPlanModel,
    KnowledgeItemModel,
    MemoryItemModel,
    RelationEdgeModel,
)
from opendocs.storage.db import build_sqlite_engine, init_db

_SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "seed_demo_data.py"
_SEED_SPEC = importlib.util.spec_from_file_location("seed_demo_data_script", _SCRIPT_PATH)
if _SEED_SPEC is None or _SEED_SPEC.loader is None:
    raise RuntimeError(f"failed to load seed script from {_SCRIPT_PATH}")
_SEED_MODULE = importlib.util.module_from_spec(_SEED_SPEC)
_SEED_SPEC.loader.exec_module(_SEED_MODULE)
seed_demo_data = _SEED_MODULE.seed_demo_data


def _count_all(engine: Engine) -> dict[str, int]:
    with Session(engine) as session:
        return {
            "documents": session.scalar(select(func.count()).select_from(DocumentModel)),
            "chunks": session.scalar(select(func.count()).select_from(ChunkModel)),
            "knowledge_items": session.scalar(select(func.count()).select_from(KnowledgeItemModel)),
            "relation_edges": session.scalar(select(func.count()).select_from(RelationEdgeModel)),
            "memory_items": session.scalar(select(func.count()).select_from(MemoryItemModel)),
            "file_operation_plans": session.scalar(
                select(func.count()).select_from(FileOperationPlanModel)
            ),
            "audit_logs": session.scalar(select(func.count()).select_from(AuditLogModel)),
        }


def test_seed_demo_data_inserts_records(db_path: Path) -> None:
    inserted = seed_demo_data(db_path)
    assert inserted == {
        "documents": 1,
        "chunks": 1,
        "knowledge_items": 1,
        "relation_edges": 1,
        "memory_items": 1,
        "file_operation_plans": 1,
        "audit_logs": 1,
    }

    engine = build_sqlite_engine(db_path)
    try:
        assert _count_all(engine) == {
            "documents": 1,
            "chunks": 1,
            "knowledge_items": 1,
            "relation_edges": 1,
            "memory_items": 1,
            "file_operation_plans": 1,
            "audit_logs": 1,
        }
        with Session(engine) as session:
            chunk = session.scalar(select(ChunkModel))
            document = session.scalar(select(DocumentModel))
            assert chunk is not None
            assert document is not None
            assert chunk.char_end <= len(chunk.text)
            assert Path(document.path).is_relative_to(db_path.parent.resolve())
    finally:
        engine.dispose()


def test_seed_demo_data_is_idempotent(db_path: Path) -> None:
    first = seed_demo_data(db_path)
    second = seed_demo_data(db_path)
    assert first["documents"] == 1
    assert second == {
        "documents": 0,
        "chunks": 0,
        "knowledge_items": 0,
        "relation_edges": 0,
        "memory_items": 0,
        "file_operation_plans": 0,
        "audit_logs": 0,
    }


def test_seed_demo_data_creates_demo_document_when_missing(db_path: Path) -> None:
    demo_doc_path, _, _ = _SEED_MODULE.resolve_seed_paths(db_path)
    demo_doc = Path(demo_doc_path)
    assert not demo_doc.exists()
    seed_demo_data(db_path)
    assert demo_doc.exists()
    assert "Project Overview" in demo_doc.read_text(encoding="utf-8")


def test_seed_demo_data_handles_existing_business_keys(db_path: Path) -> None:
    init_db(db_path)
    engine = build_sqlite_engine(db_path)
    now = datetime.now(UTC).replace(tzinfo=None)
    demo_doc_path, demo_doc_relative_path, _ = _SEED_MODULE.resolve_seed_paths(db_path)
    try:
        with Session(engine) as session:
            existing_doc_id = str(uuid.uuid4())
            session.add(
                DocumentModel(
                    doc_id=existing_doc_id,
                    path=demo_doc_path,
                    relative_path=demo_doc_relative_path,
                    source_root_id=str(uuid.uuid4()),
                    source_path=demo_doc_path,
                    hash_sha256="d" * 64,
                    title="Existing Doc",
                    file_type="md",
                    size_bytes=512,
                    created_at=now,
                    modified_at=now,
                    indexed_at=now,
                    parse_status="success",
                    category="project",
                    tags_json=["existing"],
                    sensitivity="internal",
                    is_deleted_from_fs=False,
                )
            )
            session.flush()
            session.add(
                ChunkModel(
                    chunk_id=str(uuid.uuid4()),
                    doc_id=existing_doc_id,
                    chunk_index=_SEED_MODULE.DEMO_CHUNK_INDEX,
                    text="existing chunk",
                    char_start=0,
                    char_end=12,
                )
            )
            session.add(
                MemoryItemModel(
                    memory_id=str(uuid.uuid4()),
                    memory_type="M1",
                    scope_type="task",
                    scope_id=_SEED_MODULE.DEMO_MEMORY_SCOPE_ID,
                    key=_SEED_MODULE.DEMO_MEMORY_KEY,
                    content="Bob",
                    importance=0.7,
                    status="active",
                    updated_at=now,
                )
            )
            session.commit()

        inserted = seed_demo_data(db_path)
        assert inserted["documents"] == 0
        assert inserted["chunks"] == 0
        assert inserted["memory_items"] == 0
    finally:
        engine.dispose()
