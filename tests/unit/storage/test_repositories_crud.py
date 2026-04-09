"""CRUD tests for storage repositories."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from opendocs.app import FileOperationService
from opendocs.domain.models import (
    AuditLogModel,
    ChunkModel,
    DocumentModel,
    FileOperationPlanModel,
    KnowledgeItemModel,
    MemoryItemModel,
    RelationEdgeModel,
    SourceRootModel,
    TaskEventModel,
)
from opendocs.exceptions import DeleteNotAllowedError, PlanNotApprovedError, StorageError
from opendocs.storage.repositories import (
    AuditRepository,
    ChunkRepository,
    DocumentRepository,
    IndexArtifactRepository,
    KnowledgeRepository,
    MemoryRepository,
    PlanRepository,
    RelationRepository,
    SourceRepository,
    TaskEventRepository,
)
from opendocs.utils.path_facts import (
    build_display_path,
    derive_directory_facts,
    derive_source_display_root,
)
from opendocs.utils.time import utcnow_naive


def _now() -> datetime:
    return utcnow_naive()


def _add_source_root(session: Session, *, path: str) -> SourceRootModel:
    now = _now()
    source_root_id = str(uuid.uuid4())
    source_root = SourceRootModel(
        source_root_id=source_root_id,
        path=path,
        display_root=derive_source_display_root(path, source_root_id=source_root_id),
        label="test source",
        exclude_rules_json={},
        recursive=True,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    session.add(source_root)
    session.flush()
    return source_root


def _new_document(
    path: str,
    *,
    source_root_id: str,
    file_identity: str | None = None,
    is_deleted_from_fs: bool = False,
) -> DocumentModel:
    now = _now()
    directory_path, relative_directory_path = derive_directory_facts(
        path,
        path.split("/")[-1],
    )
    return DocumentModel(
        doc_id=str(uuid.uuid4()),
        path=path,
        relative_path=path.split("/")[-1],
        display_path=build_display_path(path.split("/")[-2], path.split("/")[-1]),
        directory_path=directory_path,
        relative_directory_path=relative_directory_path,
        file_identity=file_identity,
        source_root_id=source_root_id,
        source_path=path,
        hash_sha256="b" * 64,
        title="Document",
        file_type="md",
        size_bytes=128,
        created_at=now,
        modified_at=now,
        parse_status="success",
        sensitivity="internal",
        is_deleted_from_fs=is_deleted_from_fs,
    )


def _new_chunk(doc_id: str, *, chunk_index: int = 0) -> ChunkModel:
    return ChunkModel(
        chunk_id=str(uuid.uuid4()),
        doc_id=doc_id,
        chunk_index=chunk_index,
        text="chunk text",
        char_start=0,
        char_end=10,
    )


def _new_task_event(
    *,
    chunk_id: str,
    scope_id: str,
    plan_id: str | None = None,
    trace_id: str = "trace-task-event",
    occurred_at: datetime | None = None,
) -> TaskEventModel:
    now = occurred_at or _now()
    return TaskEventModel(
        event_id=str(uuid.uuid4()),
        trace_id=trace_id,
        stage_id="S1",
        task_type="seed_demo",
        scope_type="task",
        scope_id=scope_id,
        input_summary="seed input",
        output_summary="seed output",
        related_chunk_ids_json=[chunk_id],
        evidence_refs_json=[{"chunk_id": chunk_id}],
        related_plan_id=plan_id,
        artifact_ref="C:/docs/output.md",
        occurred_at=now,
        persisted_at=now,
    )


def test_document_repository_crud(engine: Engine) -> None:
    with Session(engine) as session:
        repository = DocumentRepository(session)
        source_root = _add_source_root(session, path="C:/docs")
        document = _new_document("C:/docs/doc.md", source_root_id=source_root.source_root_id)

        repository.create(document)
        session.commit()

        fetched = repository.get_by_path("C:/docs/doc.md")
        assert fetched is not None
        assert fetched.doc_id == document.doc_id

        updated = repository.update_title(document.doc_id, "Updated Title")
        session.commit()
        assert updated is True
        assert repository.get_by_id(document.doc_id).title == "Updated Title"

        with pytest.raises(DeleteNotAllowedError, match="disabled by default"):
            repository.delete(document.doc_id)

        deleted = repository.delete(document.doc_id, allow_delete=True)
        session.commit()
        assert deleted is True
        assert repository.get_by_id(document.doc_id) is None


def test_document_repository_get_by_file_identity(engine: Engine) -> None:
    with Session(engine) as session:
        repository = DocumentRepository(session)
        source_root = _add_source_root(session, path="C:/docs")
        deleted_document = _new_document(
            "C:/docs/identity.md",
            source_root_id=source_root.source_root_id,
            file_identity="42:99",
            is_deleted_from_fs=True,
        )
        active_document = _new_document(
            "C:/docs/identity-active.md",
            source_root_id=source_root.source_root_id,
            file_identity="42:99",
        )

        repository.create(deleted_document)
        repository.create(active_document)
        session.commit()

        fetched = repository.get_by_file_identity("42:99")
        assert fetched is not None
        assert fetched.doc_id == active_document.doc_id

        fetched_deleted = repository.get_by_file_identity("42:99", include_deleted=True)
        assert fetched_deleted is not None
        assert fetched_deleted.doc_id == active_document.doc_id


def test_source_repository_updates_default_metadata(engine: Engine) -> None:
    with Session(engine) as session:
        repository = SourceRepository(session)
        source_root = _add_source_root(session, path="C:/docs")
        session.commit()

        changed = repository.update(
            source_root,
            default_category="project",
            default_tags_json=["roadmap", "alpha", "roadmap"],
            default_sensitivity="sensitive",
        )
        session.commit()

        assert changed is True
        refreshed = repository.get_by_id(source_root.source_root_id)
        assert refreshed is not None
        assert refreshed.default_category == "project"
        assert refreshed.default_tags_json == ["roadmap", "alpha", "roadmap"]
        assert refreshed.default_sensitivity == "sensitive"
        assert refreshed.source_config_rev == 2


def test_document_update_title_preserves_modified_at(engine: Engine) -> None:
    """update_title must NOT change modified_at — it is file-system mtime (§8.1.1)."""
    with Session(engine) as session:
        repository = DocumentRepository(session)
        source_root = _add_source_root(session, path="C:/docs")
        document = _new_document(
            "C:/docs/refresh-modified.md",
            source_root_id=source_root.source_root_id,
        )
        repository.create(document)
        session.commit()

        original_modified_at = repository.get_by_id(document.doc_id).modified_at

        repository.update_title(document.doc_id, "New Title")
        session.commit()

        updated = repository.get_by_id(document.doc_id)
        assert updated.title == "New Title"
        assert updated.modified_at == original_modified_at


def test_document_update_indexed_at(engine: Engine) -> None:
    """update_indexed_at sets indexed_at but NOT modified_at (§8.1.1)."""
    with Session(engine) as session:
        repository = DocumentRepository(session)
        source_root = _add_source_root(session, path="C:/docs")
        document = _new_document("C:/docs/indexed.md", source_root_id=source_root.source_root_id)
        repository.create(document)
        session.commit()

        original_modified_at = repository.get_by_id(document.doc_id).modified_at

        assert repository.update_indexed_at(document.doc_id) is True
        session.commit()

        refreshed = repository.get_by_id(document.doc_id)
        assert refreshed.indexed_at is not None
        assert refreshed.modified_at == original_modified_at

        assert repository.update_indexed_at("nonexistent-id") is False


def test_index_artifact_repository_tracks_committed_and_retained_generations(engine: Engine) -> None:
    now = utcnow_naive()
    with Session(engine) as session:
        repository = IndexArtifactRepository(session)
        repository.ensure_artifact(
            "dense_hnsw",
            namespace_path="/runtime/index/hnsw/chunks.hnsw",
            embedder_model="local-lsa-v1",
            embedder_dim=128,
            embedder_signature="sig-v1",
        )
        assert repository.try_claim_build(
            "dense_hnsw",
            namespace_path="/runtime/index/hnsw/chunks.hnsw",
            embedder_model="local-lsa-v1",
            embedder_dim=128,
            embedder_signature="sig-v1",
            build_token="token-1",
            build_started_at=now,
            lease_expires_at=now + timedelta(minutes=5),
            reason="build-1",
        )
        completed, previous_path = repository.complete_build(
            "dense_hnsw",
            build_token="token-1",
            reason="build-1",
            last_built_at=now,
            committed_bundle_path="/runtime/index/.dense_hnsw_bundles/token-1/chunks.hnsw",
            embedder_model="local-lsa-v1",
            embedder_dim=128,
            embedder_signature="sig-v1",
            retained_delete_after=now + timedelta(minutes=10),
        )
        assert completed is True
        assert previous_path is None

        assert repository.try_claim_build(
            "dense_hnsw",
            namespace_path="/runtime/index/hnsw/chunks.hnsw",
            embedder_model="local-lsa-v1",
            embedder_dim=128,
            embedder_signature="sig-v1",
            build_token="token-2",
            build_started_at=now + timedelta(minutes=1),
            lease_expires_at=now + timedelta(minutes=6),
            reason="build-2",
        )
        completed, previous_path = repository.complete_build(
            "dense_hnsw",
            build_token="token-2",
            reason="build-2",
            last_built_at=now + timedelta(minutes=1),
            committed_bundle_path="/runtime/index/.dense_hnsw_bundles/token-2/chunks.hnsw",
            embedder_model="local-lsa-v1",
            embedder_dim=128,
            embedder_signature="sig-v1",
            retained_delete_after=now + timedelta(minutes=11),
        )
        session.commit()

        assert completed is True
        assert previous_path == "/runtime/index/.dense_hnsw_bundles/token-1/chunks.hnsw"
        artifact = repository.get("dense_hnsw")
        assert artifact is not None
        assert artifact.namespace_path == "/runtime/index/hnsw/chunks.hnsw"
        generations = repository.list_generations("dense_hnsw", include_deleted=True)
        assert [row.generation for row in generations[:2]] == [2, 1]
        assert generations[0].state == "committed"
        assert generations[1].state == "retained"
        assert generations[1].delete_after is not None


def test_index_artifact_repository_rejects_legacy_building_public_status(engine: Engine) -> None:
    with Session(engine) as session:
        repository = IndexArtifactRepository(session)
        with pytest.raises(ValueError, match="invalid public artifact status"):
            repository.upsert(
                "dense_hnsw",
                status="building",
                namespace_path="/runtime/index/hnsw/chunks.hnsw",
                embedder_model="local-lsa-v1",
                embedder_dim=128,
                embedder_signature="sig-v1",
            )


def test_document_mark_deleted_from_fs(engine: Engine) -> None:
    """mark_deleted_from_fs must toggle is_deleted_from_fs flag."""
    with Session(engine) as session:
        repository = DocumentRepository(session)
        source_root = _add_source_root(session, path="C:/docs")
        document = _new_document("C:/docs/mark_del.md", source_root_id=source_root.source_root_id)
        repository.create(document)
        session.commit()
        assert repository.get_by_id(document.doc_id).is_deleted_from_fs is False

        assert repository.mark_deleted_from_fs(document.doc_id) is True
        session.commit()
        assert repository.get_by_id(document.doc_id).is_deleted_from_fs is True

        assert repository.mark_deleted_from_fs(document.doc_id, deleted=False) is True
        session.commit()
        assert repository.get_by_id(document.doc_id).is_deleted_from_fs is False

        assert repository.mark_deleted_from_fs("nonexistent-id") is False


def test_chunk_repository_crud(engine: Engine) -> None:
    with Session(engine) as session:
        source_root = _add_source_root(session, path="C:/docs")
        document = _new_document("C:/docs/chunk.md", source_root_id=source_root.source_root_id)
        DocumentRepository(session).create(document)
        session.flush()

        repository = ChunkRepository(session)
        chunk = _new_chunk(document.doc_id)
        repository.create(chunk)
        session.commit()

        chunks = repository.list_by_document(document.doc_id)
        assert len(chunks) == 1
        assert chunks[0].chunk_id == chunk.chunk_id

        assert (
            repository.update_text(
                chunk.chunk_id,
                text="updated chunk text",
                char_end=len("updated chunk text"),
            )
            is True
        )
        session.commit()
        refreshed = repository.get_by_id(chunk.chunk_id)
        assert refreshed is not None
        assert refreshed.text == "updated chunk text"
        assert refreshed.char_end == len("updated chunk text")

        with pytest.raises(DeleteNotAllowedError, match="disabled by default"):
            repository.delete(chunk.chunk_id)

        assert repository.delete(chunk.chunk_id, allow_delete=True) is True
        session.commit()
        assert repository.get_by_id(chunk.chunk_id) is None


def test_chunk_delete_by_doc_id(engine: Engine) -> None:
    """delete_by_doc_id must remove all chunks for a document."""
    with Session(engine) as session:
        source_root = _add_source_root(session, path="C:/docs")
        document = _new_document(
            "C:/docs/chunk_batch_del.md",
            source_root_id=source_root.source_root_id,
        )
        DocumentRepository(session).create(document)
        session.flush()

        repository = ChunkRepository(session)
        for i in range(3):
            repository.create(_new_chunk(document.doc_id, chunk_index=i))
        session.commit()

        assert len(repository.list_by_document(document.doc_id)) == 3

        with pytest.raises(DeleteNotAllowedError, match="disabled by default"):
            repository.delete_by_doc_id(document.doc_id)

        count = repository.delete_by_doc_id(document.doc_id, allow_delete=True)
        session.commit()
        assert count == 3
        assert len(repository.list_by_document(document.doc_id)) == 0


def test_chunk_repository_lists_chunk_ids_by_doc_ids(engine: Engine) -> None:
    with Session(engine) as session:
        source_root = _add_source_root(session, path="C:/docs")
        active_document = _new_document(
            "C:/docs/query-target.md",
            source_root_id=source_root.source_root_id,
        )
        deleted_document = _new_document(
            "C:/docs/query-deleted.md",
            source_root_id=source_root.source_root_id,
            is_deleted_from_fs=True,
        )
        DocumentRepository(session).create(active_document)
        DocumentRepository(session).create(deleted_document)
        session.flush()

        repository = ChunkRepository(session)
        active_chunk = _new_chunk(active_document.doc_id, chunk_index=0)
        deleted_chunk = _new_chunk(deleted_document.doc_id, chunk_index=0)
        repository.create(active_chunk)
        repository.create(deleted_chunk)
        session.commit()

        fetched = repository.list_chunk_ids_by_doc_ids(
            [active_document.doc_id, deleted_document.doc_id]
        )

        assert fetched == {active_chunk.chunk_id}


def test_chunk_repository_load_search_records_batches_active_document_facts(engine: Engine) -> None:
    with Session(engine) as session:
        source_root = _add_source_root(session, path="C:/docs")
        active_document = _new_document(
            "C:/docs/search-active.md",
            source_root_id=source_root.source_root_id,
        )
        deleted_document = _new_document(
            "C:/docs/search-deleted.md",
            source_root_id=source_root.source_root_id,
            is_deleted_from_fs=True,
        )
        DocumentRepository(session).create(active_document)
        DocumentRepository(session).create(deleted_document)
        session.flush()

        repository = ChunkRepository(session)
        active_chunk = ChunkModel(
            chunk_id=str(uuid.uuid4()),
            doc_id=active_document.doc_id,
            chunk_index=0,
            text="active chunk text",
            char_start=4,
            char_end=21,
            page_no=2,
            paragraph_start=0,
            paragraph_end=1,
            heading_path="Intro",
        )
        deleted_chunk = ChunkModel(
            chunk_id=str(uuid.uuid4()),
            doc_id=deleted_document.doc_id,
            chunk_index=0,
            text="deleted chunk text",
            char_start=0,
            char_end=18,
        )
        repository.create(active_chunk)
        repository.create(deleted_chunk)
        session.commit()

        fetched = repository.load_search_records([active_chunk.chunk_id, deleted_chunk.chunk_id])

        assert set(fetched) == {active_chunk.chunk_id}
        record = fetched[active_chunk.chunk_id]
        assert record.chunk_id == active_chunk.chunk_id
        assert record.doc_id == active_document.doc_id
        assert record.text == "active chunk text"
        assert record.char_start == 4
        assert record.char_end == 21
        assert record.page_no == 2
        assert record.paragraph_start == 0
        assert record.paragraph_end == 1
        assert record.heading_path == "Intro"
        assert record.title == active_document.title
        assert record.display_path == active_document.display_path
        assert record.modified_at == active_document.modified_at


def test_knowledge_repository_crud(engine: Engine) -> None:
    with Session(engine) as session:
        source_root = _add_source_root(session, path="C:/docs")
        document = _new_document(
            "C:/docs/knowledge.md",
            source_root_id=source_root.source_root_id,
        )
        DocumentRepository(session).create(document)
        chunk = _new_chunk(document.doc_id)
        ChunkRepository(session).create(chunk)
        session.flush()

        repository = KnowledgeRepository(session)
        knowledge = KnowledgeItemModel(
            knowledge_id=str(uuid.uuid4()),
            doc_id=document.doc_id,
            chunk_id=chunk.chunk_id,
            summary="initial summary",
            entities_json=["OpenDocs"],
            topics_json=["baseline"],
            confidence=0.8,
        )
        repository.create(knowledge)
        session.commit()

        fetched = repository.get_by_id(knowledge.knowledge_id)
        assert fetched is not None
        assert fetched.summary == "initial summary"

        by_doc = repository.list_by_document(document.doc_id)
        assert len(by_doc) == 1
        assert by_doc[0].knowledge_id == knowledge.knowledge_id

        assert repository.update_summary(knowledge.knowledge_id, "updated summary", 0.9) is True
        session.commit()
        updated = repository.get_by_id(knowledge.knowledge_id)
        assert updated is not None
        assert updated.summary == "updated summary"
        assert updated.confidence == 0.9

        with pytest.raises(DeleteNotAllowedError, match="disabled by default"):
            repository.delete(knowledge.knowledge_id)

        assert repository.delete(knowledge.knowledge_id, allow_delete=True) is True
        session.commit()
        assert repository.get_by_id(knowledge.knowledge_id) is None


def test_relation_repository_crud(engine: Engine) -> None:
    with Session(engine) as session:
        source_root = _add_source_root(session, path="C:/docs")
        document = _new_document(
            "C:/docs/relation.md",
            source_root_id=source_root.source_root_id,
        )
        DocumentRepository(session).create(document)
        chunk = _new_chunk(document.doc_id)
        ChunkRepository(session).create(chunk)
        session.flush()

        repository = RelationRepository(session)
        edge = RelationEdgeModel(
            edge_id=str(uuid.uuid4()),
            src_type="document",
            src_id=document.doc_id,
            dst_type="chunk",
            dst_id=chunk.chunk_id,
            relation_type="derived_from",
            weight=0.6,
            evidence_chunk_id=chunk.chunk_id,
        )
        repository.create(edge)
        session.commit()

        fetched = repository.get_by_id(edge.edge_id)
        assert fetched is not None
        assert fetched.weight == 0.6

        by_source = repository.list_by_source("document", document.doc_id)
        assert len(by_source) == 1
        assert by_source[0].edge_id == edge.edge_id

        assert repository.update_weight(edge.edge_id, 0.95) is True
        session.commit()
        updated = repository.get_by_id(edge.edge_id)
        assert updated is not None
        assert updated.weight == 0.95

        with pytest.raises(DeleteNotAllowedError, match="disabled by default"):
            repository.delete(edge.edge_id)

        assert repository.delete(edge.edge_id, allow_delete=True) is True
        session.commit()
        assert repository.get_by_id(edge.edge_id) is None


def test_memory_repository_crud(engine: Engine) -> None:
    with Session(engine) as session:
        source_root = _add_source_root(session, path="C:/docs")
        document = _new_document("C:/docs/memory.md", source_root_id=source_root.source_root_id)
        DocumentRepository(session).create(document)
        chunk = _new_chunk(document.doc_id)
        ChunkRepository(session).create(chunk)
        task_event = _new_task_event(chunk_id=chunk.chunk_id, scope_id="task-001")
        TaskEventRepository(session).create(task_event)

        repository = MemoryRepository(session)
        memory = MemoryItemModel(
            memory_id=str(uuid.uuid4()),
            memory_type="M1",
            memory_kind="task_snapshot",
            scope_type="task",
            scope_id="task-001",
            key="deadline",
            content="2026-03-31",
            source_event_ids_json=[task_event.event_id],
            evidence_refs_json=[{"chunk_id": chunk.chunk_id}],
            importance=0.9,
            confidence=0.85,
            status="active",
            review_window_days=30,
            user_confirmed_count=0,
            recall_count=0,
            decay_score=0.0,
            promotion_state="promoted",
            consolidated_from_json=[],
            updated_at=_now() - timedelta(seconds=5),
        )
        repository.create(memory)
        session.commit()

        fetched = repository.get_by_scope_key(
            memory_type="M1",
            scope_type="task",
            scope_id="task-001",
            key="deadline",
        )
        assert fetched is not None
        assert fetched.memory_id == memory.memory_id

        previous_updated_at = fetched.updated_at
        assert repository.update_status(memory.memory_id, "disabled") is True
        session.commit()
        updated = repository.get_by_id(memory.memory_id)
        assert updated.status == "disabled"
        assert updated.updated_at > previous_updated_at

        with pytest.raises(DeleteNotAllowedError, match="disabled by default"):
            repository.delete(memory.memory_id)

        assert repository.delete(memory.memory_id, allow_delete=True) is True
        session.commit()
        assert repository.get_by_id(memory.memory_id) is None


def test_task_event_repository_crud(engine: Engine) -> None:
    with Session(engine) as session:
        source_root = _add_source_root(session, path="C:/docs")
        document = _new_document("C:/docs/task-event.md", source_root_id=source_root.source_root_id)
        DocumentRepository(session).create(document)
        chunk = _new_chunk(document.doc_id)
        ChunkRepository(session).create(chunk)
        plan = FileOperationPlanModel(
            plan_id=str(uuid.uuid4()),
            operation_type="move",
            status="draft",
            item_count=1,
            risk_level="low",
            preview_json={"items": [{"from": "a", "to": "b"}]},
        )
        PlanRepository(session).create(plan)

        repository = TaskEventRepository(session)
        first = _new_task_event(
            chunk_id=chunk.chunk_id,
            scope_id="task-events",
            plan_id=plan.plan_id,
            trace_id="trace-task-events",
            occurred_at=_now() - timedelta(minutes=1),
        )
        second = _new_task_event(
            chunk_id=chunk.chunk_id,
            scope_id="task-events",
            trace_id="trace-task-events",
            occurred_at=_now(),
        )
        repository.create(first)
        repository.create(second)
        session.commit()

        fetched = repository.get_by_id(first.event_id)
        assert fetched is not None
        assert fetched.related_plan_id == plan.plan_id

        by_business_key = repository.find_by_business_key(
            trace_id="trace-task-events",
            stage_id="S1",
            task_type="seed_demo",
            scope_type="task",
            scope_id="task-events",
        )
        assert by_business_key is not None
        assert by_business_key.event_id == second.event_id

        by_scope = repository.list_by_scope(scope_type="task", scope_id="task-events")
        assert [event.event_id for event in by_scope] == [second.event_id, first.event_id]

        by_trace = repository.list_by_trace("trace-task-events")
        assert [event.event_id for event in by_trace] == [second.event_id, first.event_id]


def test_memory_repository_rejects_non_persistent_memory_types(engine: Engine) -> None:
    with Session(engine) as session:
        repository = MemoryRepository(session)

        with pytest.raises(StorageError, match="only M1/M2 memories may be persisted"):
            repository.create(
                MemoryItemModel(
                    memory_id=str(uuid.uuid4()),
                    memory_type="M0",
                    memory_kind="task_snapshot",
                    scope_type="task",
                    scope_id="session-001",
                    key="status",
                    content="ready",
                    source_event_ids_json=["missing-event"],
                    evidence_refs_json=[],
                    importance=0.5,
                    confidence=0.5,
                    status="active",
                    review_window_days=30,
                    user_confirmed_count=0,
                    recall_count=0,
                    decay_score=0.0,
                    promotion_state="promoted",
                    consolidated_from_json=[],
                )
            )

        session.rollback()
        assert session.query(MemoryItemModel).count() == 0


def test_memory_repository_rejects_missing_task_event_reference(engine: Engine) -> None:
    with Session(engine) as session:
        repository = MemoryRepository(session)

        with pytest.raises(StorageError, match="must reference real task events"):
            repository.create(
                MemoryItemModel(
                    memory_id=str(uuid.uuid4()),
                    memory_type="M1",
                    memory_kind="task_snapshot",
                    scope_type="task",
                    scope_id="task-001",
                    key="status",
                    content="ready",
                    source_event_ids_json=[str(uuid.uuid4())],
                    evidence_refs_json=[],
                    importance=0.5,
                    confidence=0.5,
                    status="active",
                    review_window_days=30,
                    user_confirmed_count=0,
                    recall_count=0,
                    decay_score=0.0,
                    promotion_state="promoted",
                    consolidated_from_json=[],
                )
            )

        session.rollback()
        assert session.query(MemoryItemModel).count() == 0


def test_memory_list_active_by_scope(engine: Engine) -> None:
    with Session(engine) as session:
        source_root = _add_source_root(session, path="C:/docs")
        document = _new_document("C:/docs/memory-list.md", source_root_id=source_root.source_root_id)
        DocumentRepository(session).create(document)
        chunk = _new_chunk(document.doc_id)
        ChunkRepository(session).create(chunk)
        promoted_event = _new_task_event(chunk_id=chunk.chunk_id, scope_id="task-list-scope")
        candidate_event = _new_task_event(chunk_id=chunk.chunk_id, scope_id="task-list-scope")
        other_event = _new_task_event(chunk_id=chunk.chunk_id, scope_id="other-scope")
        task_events = TaskEventRepository(session)
        for event in (promoted_event, candidate_event, other_event):
            task_events.create(event)

        repository = MemoryRepository(session)
        scope_id = "task-list-scope"

        active_m1 = MemoryItemModel(
            memory_id=str(uuid.uuid4()),
            memory_type="M1",
            memory_kind="task_snapshot",
            scope_type="task",
            scope_id=scope_id,
            key="goal",
            content="finish report",
            source_event_ids_json=[promoted_event.event_id],
            evidence_refs_json=[],
            importance=0.8,
            confidence=0.9,
            status="active",
            review_window_days=30,
            user_confirmed_count=0,
            recall_count=0,
            decay_score=0.0,
            promotion_state="promoted",
            consolidated_from_json=[],
            updated_at=_now(),
        )
        active_m2 = MemoryItemModel(
            memory_id=str(uuid.uuid4()),
            memory_type="M2",
            memory_kind="preference_pattern",
            scope_type="task",
            scope_id=scope_id,
            key="style",
            content="concise",
            source_event_ids_json=[promoted_event.event_id],
            evidence_refs_json=[],
            importance=0.5,
            confidence=0.95,
            status="active",
            review_window_days=30,
            user_confirmed_count=0,
            recall_count=0,
            decay_score=0.0,
            promotion_state="promoted",
            consolidated_from_json=[],
            updated_at=_now(),
        )
        candidate_m2 = MemoryItemModel(
            memory_id=str(uuid.uuid4()),
            memory_type="M2",
            memory_kind="preference_pattern",
            scope_type="task",
            scope_id=scope_id,
            key="format",
            content="bullet list",
            source_event_ids_json=[candidate_event.event_id],
            evidence_refs_json=[],
            importance=0.7,
            confidence=0.6,
            status="active",
            review_window_days=30,
            user_confirmed_count=0,
            recall_count=0,
            decay_score=0.0,
            promotion_state="candidate",
            consolidated_from_json=[],
            updated_at=_now(),
        )
        expired_m1 = MemoryItemModel(
            memory_id=str(uuid.uuid4()),
            memory_type="M1",
            memory_kind="task_snapshot",
            scope_type="task",
            scope_id=scope_id,
            key="old_note",
            content="stale",
            source_event_ids_json=[promoted_event.event_id],
            evidence_refs_json=[],
            importance=0.3,
            confidence=0.4,
            status="expired",
            review_window_days=30,
            user_confirmed_count=0,
            recall_count=0,
            decay_score=0.8,
            promotion_state="promoted",
            consolidated_from_json=[],
            updated_at=_now(),
        )
        other_scope = MemoryItemModel(
            memory_id=str(uuid.uuid4()),
            memory_type="M1",
            memory_kind="workflow_hint",
            scope_type="task",
            scope_id="other-scope",
            key="unrelated",
            content="noise",
            source_event_ids_json=[other_event.event_id],
            evidence_refs_json=[],
            importance=1.0,
            confidence=0.7,
            status="active",
            review_window_days=30,
            user_confirmed_count=0,
            recall_count=0,
            decay_score=0.0,
            promotion_state="promoted",
            consolidated_from_json=[],
            updated_at=_now(),
        )
        for item in [active_m1, active_m2, candidate_m2, expired_m1, other_scope]:
            repository.create(item)
        session.commit()

        # All active items for the scope, ordered by importance desc
        results = repository.list_active_by_scope(scope_type="task", scope_id=scope_id)
        result_ids = [r.memory_id for r in results]
        assert len(results) == 2
        assert active_m1.memory_id in result_ids
        assert active_m2.memory_id in result_ids
        assert candidate_m2.memory_id not in result_ids
        assert expired_m1.memory_id not in result_ids
        assert other_scope.memory_id not in result_ids
        assert results[0].importance >= results[1].importance

        # Filter by memory_type
        m1_only = repository.list_active_by_scope(
            scope_type="task", scope_id=scope_id, memory_type="M1"
        )
        assert len(m1_only) == 1
        assert m1_only[0].memory_id == active_m1.memory_id


def test_plan_repository_crud(engine: Engine) -> None:
    with Session(engine) as session:
        repository = PlanRepository(session)
        plan = FileOperationPlanModel(
            plan_id=str(uuid.uuid4()),
            operation_type="move",
            status="draft",
            item_count=2,
            risk_level="medium",
            preview_json={"items": [{"from": "a", "to": "b"}]},
        )
        repository.create(plan)
        session.commit()

        assert repository.get_by_id(plan.plan_id) is not None
        assert len(repository.list_by_status("draft")) == 1

        assert repository.update_status(plan.plan_id, "approved") is True
        session.commit()
        approved = repository.get_by_id(plan.plan_id)
        assert approved.status == "approved"
        assert approved.approved_at is not None

        with pytest.raises(
            PlanNotApprovedError,
            match="must use FileOperationService.execute_plan",
        ):
            repository.update_status(plan.plan_id, "executed")

        service = FileOperationService(session, operation_executor=lambda _plan: None)
        executed, _audit = service.execute_plan(
            plan.plan_id,
            actor="system",
            trace_id="trace-plan-execute",
        )
        session.commit()
        assert executed.status == "executed"
        assert executed.executed_at is not None

        with pytest.raises(DeleteNotAllowedError, match="disabled by default"):
            repository.delete(plan.plan_id)

        assert repository.delete(plan.plan_id, allow_delete=True) is True
        session.commit()
        assert repository.get_by_id(plan.plan_id) is None


def test_plan_repository_rejects_executed_at_override(engine: Engine) -> None:
    with Session(engine) as session:
        repository = PlanRepository(session)
        plan = FileOperationPlanModel(
            plan_id=str(uuid.uuid4()),
            operation_type="move",
            status="draft",
            item_count=1,
            risk_level="low",
            preview_json={"items": [{"from": "a", "to": "b"}]},
        )
        repository.create(plan)
        session.commit()

        candidate_executed_at = _now()
        with pytest.raises(
            ValueError,
            match="managed only by FileOperationService.execute_plan",
        ):
            repository.update_status(
                plan.plan_id,
                "approved",
                executed_at=candidate_executed_at,
            )

        assert repository.update_status(plan.plan_id, "approved") is True
        session.commit()

        refreshed = repository.get_by_id(plan.plan_id)
        assert refreshed.status == "approved"
        assert refreshed.executed_at is None


def test_plan_repository_has_no_internal_executed_escape_hatch(engine: Engine) -> None:
    with Session(engine) as session:
        repository = PlanRepository(session)
        plan = FileOperationPlanModel(
            plan_id=str(uuid.uuid4()),
            operation_type="move",
            status="draft",
            item_count=1,
            risk_level="low",
            preview_json={"items": [{"from": "a", "to": "b"}]},
        )
        repository.create(plan)
        session.commit()

        with pytest.raises(TypeError, match="_internal"):
            repository.update_status(plan.plan_id, "executed", _internal=True)


def test_audit_repository_query(engine: Engine) -> None:
    with Session(engine) as session:
        repository = AuditRepository(session)
        now = _now()
        log1 = AuditLogModel(
            audit_id=str(uuid.uuid4()),
            timestamp=now - timedelta(minutes=5),
            actor="system",
            operation="index",
            target_type="document",
            target_id="doc-1",
            result="success",
            detail_json={"file_path": "C:/docs/a.md", "task_id": "task-1"},
            trace_id="trace-task-1",
        )
        log2 = AuditLogModel(
            audit_id=str(uuid.uuid4()),
            timestamp=now - timedelta(minutes=2),
            actor="user",
            operation="qa",
            target_type="answer",
            target_id="ans-1",
            result="success",
            detail_json={"file_path": "C:/docs/b.md", "task_id": "task-1"},
            trace_id="trace-task-1",
        )
        log3 = AuditLogModel(
            audit_id=str(uuid.uuid4()),
            timestamp=now - timedelta(minutes=10),
            actor="system",
            operation="index",
            target_type="document",
            target_id="doc-2",
            result="success",
            detail_json={"file_path": "C:/docs/a.md.bak", "task_id": "task-2"},
            trace_id="trace-task-2",
        )
        repository.create(log1)
        repository.create(log2)
        repository.create(log3)
        session.commit()

        with pytest.raises(StorageError, match="append-only"):
            repository.update_detail(
                log2.audit_id,
                detail_json={"file_path": "C:/docs/b.md", "task_id": "task-1", "updated": True},
                result="failure",
            )

        session.rollback()
        unchanged_log2 = repository.get_by_id(log2.audit_id)
        assert unchanged_log2 is not None
        assert unchanged_log2.result == "success"
        assert unchanged_log2.detail_json == {"file_path": "C:/docs/b.md", "task_id": "task-1"}

        by_trace = repository.query(trace_id="trace-task-1")
        assert len(by_trace) == 2
        assert [entry.audit_id for entry in by_trace] == [log2.audit_id, log1.audit_id]

        by_file = repository.query(file_path="C:/docs/b.md")
        assert len(by_file) == 1
        assert by_file[0].audit_id == log2.audit_id

        by_task = repository.query(task_id="task-1")
        assert len(by_task) == 2
        assert [entry.audit_id for entry in by_task] == [log2.audit_id, log1.audit_id]

        exact_file = repository.query(file_path="C:/docs/a.md")
        assert len(exact_file) == 1
        assert exact_file[0].audit_id == log1.audit_id

        by_time = repository.query(start_time=now - timedelta(minutes=3), end_time=now)
        assert len(by_time) == 1
        assert by_time[0].audit_id == log2.audit_id

        with pytest.raises(DeleteNotAllowedError, match="append-only"):
            repository.delete(log3.audit_id)

        with pytest.raises(DeleteNotAllowedError, match="append-only"):
            repository.delete(log3.audit_id, allow_delete=True)

        assert repository.get_by_id(log3.audit_id) is not None


def test_audit_query_returns_all_without_limit(engine: Engine) -> None:
    """query(limit=None) must return all audit logs without truncation."""
    with Session(engine) as session:
        repository = AuditRepository(session)
        for i in range(5):
            repository.create(
                AuditLogModel(
                    audit_id=str(uuid.uuid4()),
                    actor="system",
                    operation="test_op",
                    target_type="plan",
                    target_id=f"plan-{i}",
                    result="success",
                    detail_json={},
                    trace_id=f"trace-nolimit-{i}",
                )
            )
        session.commit()

        all_logs = repository.query(limit=None)
        assert len(all_logs) == 5

        limited = repository.query(limit=2)
        assert len(limited) == 2


def test_document_list_all_returns_all_without_limit(engine: Engine) -> None:
    """list_all() with no limit must return all documents, not just 100."""
    with Session(engine) as session:
        repository = DocumentRepository(session)
        source_root = _add_source_root(session, path="C:/docs")
        paths = [f"C:/docs/list_all_{i:03d}.md" for i in range(5)]
        for path in paths:
            repository.create(_new_document(path, source_root_id=source_root.source_root_id))
        session.commit()

        all_docs = repository.list_all()
        assert len(all_docs) == 5

        limited = repository.list_all(limit=2)
        assert len(limited) == 2


def test_document_get_by_path(engine: Engine) -> None:
    """get_by_path must resolve the current active document for a path."""
    with Session(engine) as session:
        repository = DocumentRepository(session)
        source_root = _add_source_root(session, path="C:/docs")
        doc = _new_document("C:/docs/by_path_test.md", source_root_id=source_root.source_root_id)
        repository.create(doc)
        session.commit()

        found = repository.get_by_path("C:/docs/by_path_test.md")
        assert found is not None
        assert found.doc_id == doc.doc_id

        missing = repository.get_by_path("C:/docs/nonexistent.md")
        assert missing is None


def test_document_get_by_path_ignores_deleted_lineage(engine: Engine) -> None:
    with Session(engine) as session:
        repository = DocumentRepository(session)
        source_root = _add_source_root(session, path="C:/docs")
        deleted = _new_document(
            "C:/docs/reused.md",
            source_root_id=source_root.source_root_id,
            is_deleted_from_fs=True,
        )
        active = _new_document("C:/docs/reused.md", source_root_id=source_root.source_root_id)
        repository.create(deleted)
        repository.create(active)
        session.commit()

        found = repository.get_by_path("C:/docs/reused.md")
        assert found is not None
        assert found.doc_id == active.doc_id


def test_cascade_delete_removes_chunks_and_knowledge(engine: Engine) -> None:
    """Deleting a document must cascade-delete its chunks and knowledge items."""
    with Session(engine) as session:
        source_root = _add_source_root(session, path="C:/docs")
        doc = _new_document("C:/docs/cascade.md", source_root_id=source_root.source_root_id)
        DocumentRepository(session).create(doc)
        session.flush()

        chunk = _new_chunk(doc.doc_id, chunk_index=0)
        ChunkRepository(session).create(chunk)
        session.flush()

        ki = KnowledgeItemModel(
            knowledge_id=str(uuid.uuid4()),
            doc_id=doc.doc_id,
            chunk_id=chunk.chunk_id,
            summary="test",
            confidence=0.5,
        )
        KnowledgeRepository(session).create(ki)
        session.commit()

        chunk_id = chunk.chunk_id
        ki_id = ki.knowledge_id

        assert ChunkRepository(session).get_by_id(chunk_id) is not None
        assert KnowledgeRepository(session).get_by_id(ki_id) is not None

        DocumentRepository(session).delete(doc.doc_id, allow_delete=True)
        session.commit()

    # Use a fresh session to avoid SQLAlchemy identity map caching
    with Session(engine) as session2:
        assert ChunkRepository(session2).get_by_id(chunk_id) is None
        assert KnowledgeRepository(session2).get_by_id(ki_id) is None


def test_cascade_delete_nullifies_relation_edge_evidence(engine: Engine) -> None:
    """Deleting a chunk must SET NULL the evidence_chunk_id on relation edges."""
    with Session(engine) as session:
        source_root = _add_source_root(session, path="C:/docs")
        doc = _new_document("C:/docs/cascade_rel.md", source_root_id=source_root.source_root_id)
        DocumentRepository(session).create(doc)
        session.flush()

        chunk = _new_chunk(doc.doc_id, chunk_index=0)
        ChunkRepository(session).create(chunk)
        session.flush()

        edge = RelationEdgeModel(
            edge_id=str(uuid.uuid4()),
            src_type="document",
            src_id=doc.doc_id,
            dst_type="document",
            dst_id=str(uuid.uuid4()),
            relation_type="related_to",
            weight=1.0,
            evidence_chunk_id=chunk.chunk_id,
        )
        RelationRepository(session).create(edge)
        session.commit()

        assert RelationRepository(session).get_by_id(edge.edge_id).evidence_chunk_id is not None

        ChunkRepository(session).delete(chunk.chunk_id, allow_delete=True)
        session.commit()

        refreshed = RelationRepository(session).get_by_id(edge.edge_id)
        assert refreshed is not None
        assert refreshed.evidence_chunk_id is None


def test_memory_scope_key_unique_constraint(engine: Engine) -> None:
    """Duplicate (memory_type, scope_type, scope_id, key) must be rejected."""
    with Session(engine) as session:
        repository = MemoryRepository(session)
        base = dict(
            memory_type="M1",
            memory_kind="task_snapshot",
            scope_type="task",
            scope_id="task-dup",
            key="status",
            content="in progress",
            source_event_ids_json=[],
            evidence_refs_json=[],
            importance=0.5,
            confidence=0.6,
            status="active",
            review_window_days=30,
            user_confirmed_count=0,
            recall_count=0,
            decay_score=0.0,
            promotion_state="promoted",
            consolidated_from_json=[],
        )
        source_root = _add_source_root(session, path="C:/docs")
        document = _new_document("C:/docs/dup.md", source_root_id=source_root.source_root_id)
        DocumentRepository(session).create(document)
        chunk = _new_chunk(document.doc_id)
        ChunkRepository(session).create(chunk)
        task_event = _new_task_event(chunk_id=chunk.chunk_id, scope_id="task-dup")
        TaskEventRepository(session).create(task_event)
        repository.create(
            MemoryItemModel(
                memory_id=str(uuid.uuid4()),
                **{**base, "source_event_ids_json": [task_event.event_id]},
            )
        )
        session.commit()

        from sqlalchemy.exc import IntegrityError

        with pytest.raises(IntegrityError):
            repository.create(
                MemoryItemModel(
                    memory_id=str(uuid.uuid4()),
                    **{
                        **base,
                        "content": "duplicate",
                        "source_event_ids_json": [task_event.event_id],
                    },
                )
            )
