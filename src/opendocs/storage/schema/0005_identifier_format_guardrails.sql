-- Backfill UUID / SHA256 identifier format guardrails for legacy databases.

CREATE TRIGGER ck_documents_doc_id_uuid_insert
BEFORE INSERT ON documents
WHEN
    NEW.doc_id IS NULL
    OR length(NEW.doc_id) != 36
    OR substr(NEW.doc_id, 9, 1) != '-'
    OR substr(NEW.doc_id, 14, 1) != '-'
    OR substr(NEW.doc_id, 19, 1) != '-'
    OR substr(NEW.doc_id, 24, 1) != '-'
    OR length(replace(NEW.doc_id, '-', '')) != 32
    OR lower(NEW.doc_id) != NEW.doc_id
    OR replace(NEW.doc_id, '-', '') GLOB '*[^0-9a-f]*'
BEGIN
    SELECT RAISE(ABORT, 'ck_documents_doc_id_uuid');
END;

CREATE TRIGGER ck_documents_doc_id_uuid_update
BEFORE UPDATE OF doc_id ON documents
WHEN
    NEW.doc_id IS NULL
    OR length(NEW.doc_id) != 36
    OR substr(NEW.doc_id, 9, 1) != '-'
    OR substr(NEW.doc_id, 14, 1) != '-'
    OR substr(NEW.doc_id, 19, 1) != '-'
    OR substr(NEW.doc_id, 24, 1) != '-'
    OR length(replace(NEW.doc_id, '-', '')) != 32
    OR lower(NEW.doc_id) != NEW.doc_id
    OR replace(NEW.doc_id, '-', '') GLOB '*[^0-9a-f]*'
BEGIN
    SELECT RAISE(ABORT, 'ck_documents_doc_id_uuid');
END;

CREATE TRIGGER ck_documents_source_root_id_uuid_insert
BEFORE INSERT ON documents
WHEN
    NEW.source_root_id IS NULL
    OR length(NEW.source_root_id) != 36
    OR substr(NEW.source_root_id, 9, 1) != '-'
    OR substr(NEW.source_root_id, 14, 1) != '-'
    OR substr(NEW.source_root_id, 19, 1) != '-'
    OR substr(NEW.source_root_id, 24, 1) != '-'
    OR length(replace(NEW.source_root_id, '-', '')) != 32
    OR lower(NEW.source_root_id) != NEW.source_root_id
    OR replace(NEW.source_root_id, '-', '') GLOB '*[^0-9a-f]*'
BEGIN
    SELECT RAISE(ABORT, 'ck_documents_source_root_id_uuid');
END;

CREATE TRIGGER ck_documents_source_root_id_uuid_update
BEFORE UPDATE OF source_root_id ON documents
WHEN
    NEW.source_root_id IS NULL
    OR length(NEW.source_root_id) != 36
    OR substr(NEW.source_root_id, 9, 1) != '-'
    OR substr(NEW.source_root_id, 14, 1) != '-'
    OR substr(NEW.source_root_id, 19, 1) != '-'
    OR substr(NEW.source_root_id, 24, 1) != '-'
    OR length(replace(NEW.source_root_id, '-', '')) != 32
    OR lower(NEW.source_root_id) != NEW.source_root_id
    OR replace(NEW.source_root_id, '-', '') GLOB '*[^0-9a-f]*'
BEGIN
    SELECT RAISE(ABORT, 'ck_documents_source_root_id_uuid');
END;

CREATE TRIGGER ck_documents_hash_sha256_insert
BEFORE INSERT ON documents
WHEN
    NEW.hash_sha256 IS NULL
    OR length(NEW.hash_sha256) != 64
    OR lower(NEW.hash_sha256) != NEW.hash_sha256
    OR NEW.hash_sha256 GLOB '*[^0-9a-f]*'
BEGIN
    SELECT RAISE(ABORT, 'ck_documents_hash_sha256');
END;

CREATE TRIGGER ck_documents_hash_sha256_update
BEFORE UPDATE OF hash_sha256 ON documents
WHEN
    NEW.hash_sha256 IS NULL
    OR length(NEW.hash_sha256) != 64
    OR lower(NEW.hash_sha256) != NEW.hash_sha256
    OR NEW.hash_sha256 GLOB '*[^0-9a-f]*'
BEGIN
    SELECT RAISE(ABORT, 'ck_documents_hash_sha256');
END;

CREATE TRIGGER ck_chunks_chunk_id_uuid_insert
BEFORE INSERT ON chunks
WHEN
    NEW.chunk_id IS NULL
    OR length(NEW.chunk_id) != 36
    OR substr(NEW.chunk_id, 9, 1) != '-'
    OR substr(NEW.chunk_id, 14, 1) != '-'
    OR substr(NEW.chunk_id, 19, 1) != '-'
    OR substr(NEW.chunk_id, 24, 1) != '-'
    OR length(replace(NEW.chunk_id, '-', '')) != 32
    OR lower(NEW.chunk_id) != NEW.chunk_id
    OR replace(NEW.chunk_id, '-', '') GLOB '*[^0-9a-f]*'
BEGIN
    SELECT RAISE(ABORT, 'ck_chunks_chunk_id_uuid');
END;

CREATE TRIGGER ck_chunks_chunk_id_uuid_update
BEFORE UPDATE OF chunk_id ON chunks
WHEN
    NEW.chunk_id IS NULL
    OR length(NEW.chunk_id) != 36
    OR substr(NEW.chunk_id, 9, 1) != '-'
    OR substr(NEW.chunk_id, 14, 1) != '-'
    OR substr(NEW.chunk_id, 19, 1) != '-'
    OR substr(NEW.chunk_id, 24, 1) != '-'
    OR length(replace(NEW.chunk_id, '-', '')) != 32
    OR lower(NEW.chunk_id) != NEW.chunk_id
    OR replace(NEW.chunk_id, '-', '') GLOB '*[^0-9a-f]*'
BEGIN
    SELECT RAISE(ABORT, 'ck_chunks_chunk_id_uuid');
END;

CREATE TRIGGER ck_chunks_doc_id_uuid_insert
BEFORE INSERT ON chunks
WHEN
    NEW.doc_id IS NULL
    OR length(NEW.doc_id) != 36
    OR substr(NEW.doc_id, 9, 1) != '-'
    OR substr(NEW.doc_id, 14, 1) != '-'
    OR substr(NEW.doc_id, 19, 1) != '-'
    OR substr(NEW.doc_id, 24, 1) != '-'
    OR length(replace(NEW.doc_id, '-', '')) != 32
    OR lower(NEW.doc_id) != NEW.doc_id
    OR replace(NEW.doc_id, '-', '') GLOB '*[^0-9a-f]*'
BEGIN
    SELECT RAISE(ABORT, 'ck_chunks_doc_id_uuid');
END;

CREATE TRIGGER ck_chunks_doc_id_uuid_update
BEFORE UPDATE OF doc_id ON chunks
WHEN
    NEW.doc_id IS NULL
    OR length(NEW.doc_id) != 36
    OR substr(NEW.doc_id, 9, 1) != '-'
    OR substr(NEW.doc_id, 14, 1) != '-'
    OR substr(NEW.doc_id, 19, 1) != '-'
    OR substr(NEW.doc_id, 24, 1) != '-'
    OR length(replace(NEW.doc_id, '-', '')) != 32
    OR lower(NEW.doc_id) != NEW.doc_id
    OR replace(NEW.doc_id, '-', '') GLOB '*[^0-9a-f]*'
BEGIN
    SELECT RAISE(ABORT, 'ck_chunks_doc_id_uuid');
END;

CREATE TRIGGER ck_knowledge_items_knowledge_id_uuid_insert
BEFORE INSERT ON knowledge_items
WHEN
    NEW.knowledge_id IS NULL
    OR length(NEW.knowledge_id) != 36
    OR substr(NEW.knowledge_id, 9, 1) != '-'
    OR substr(NEW.knowledge_id, 14, 1) != '-'
    OR substr(NEW.knowledge_id, 19, 1) != '-'
    OR substr(NEW.knowledge_id, 24, 1) != '-'
    OR length(replace(NEW.knowledge_id, '-', '')) != 32
    OR lower(NEW.knowledge_id) != NEW.knowledge_id
    OR replace(NEW.knowledge_id, '-', '') GLOB '*[^0-9a-f]*'
BEGIN
    SELECT RAISE(ABORT, 'ck_knowledge_items_knowledge_id_uuid');
END;

CREATE TRIGGER ck_knowledge_items_knowledge_id_uuid_update
BEFORE UPDATE OF knowledge_id ON knowledge_items
WHEN
    NEW.knowledge_id IS NULL
    OR length(NEW.knowledge_id) != 36
    OR substr(NEW.knowledge_id, 9, 1) != '-'
    OR substr(NEW.knowledge_id, 14, 1) != '-'
    OR substr(NEW.knowledge_id, 19, 1) != '-'
    OR substr(NEW.knowledge_id, 24, 1) != '-'
    OR length(replace(NEW.knowledge_id, '-', '')) != 32
    OR lower(NEW.knowledge_id) != NEW.knowledge_id
    OR replace(NEW.knowledge_id, '-', '') GLOB '*[^0-9a-f]*'
BEGIN
    SELECT RAISE(ABORT, 'ck_knowledge_items_knowledge_id_uuid');
END;

CREATE TRIGGER ck_knowledge_items_doc_id_uuid_insert
BEFORE INSERT ON knowledge_items
WHEN
    NEW.doc_id IS NULL
    OR length(NEW.doc_id) != 36
    OR substr(NEW.doc_id, 9, 1) != '-'
    OR substr(NEW.doc_id, 14, 1) != '-'
    OR substr(NEW.doc_id, 19, 1) != '-'
    OR substr(NEW.doc_id, 24, 1) != '-'
    OR length(replace(NEW.doc_id, '-', '')) != 32
    OR lower(NEW.doc_id) != NEW.doc_id
    OR replace(NEW.doc_id, '-', '') GLOB '*[^0-9a-f]*'
BEGIN
    SELECT RAISE(ABORT, 'ck_knowledge_items_doc_id_uuid');
END;

CREATE TRIGGER ck_knowledge_items_doc_id_uuid_update
BEFORE UPDATE OF doc_id ON knowledge_items
WHEN
    NEW.doc_id IS NULL
    OR length(NEW.doc_id) != 36
    OR substr(NEW.doc_id, 9, 1) != '-'
    OR substr(NEW.doc_id, 14, 1) != '-'
    OR substr(NEW.doc_id, 19, 1) != '-'
    OR substr(NEW.doc_id, 24, 1) != '-'
    OR length(replace(NEW.doc_id, '-', '')) != 32
    OR lower(NEW.doc_id) != NEW.doc_id
    OR replace(NEW.doc_id, '-', '') GLOB '*[^0-9a-f]*'
BEGIN
    SELECT RAISE(ABORT, 'ck_knowledge_items_doc_id_uuid');
END;

CREATE TRIGGER ck_knowledge_items_chunk_id_uuid_insert
BEFORE INSERT ON knowledge_items
WHEN
    NEW.chunk_id IS NULL
    OR length(NEW.chunk_id) != 36
    OR substr(NEW.chunk_id, 9, 1) != '-'
    OR substr(NEW.chunk_id, 14, 1) != '-'
    OR substr(NEW.chunk_id, 19, 1) != '-'
    OR substr(NEW.chunk_id, 24, 1) != '-'
    OR length(replace(NEW.chunk_id, '-', '')) != 32
    OR lower(NEW.chunk_id) != NEW.chunk_id
    OR replace(NEW.chunk_id, '-', '') GLOB '*[^0-9a-f]*'
BEGIN
    SELECT RAISE(ABORT, 'ck_knowledge_items_chunk_id_uuid');
END;

CREATE TRIGGER ck_knowledge_items_chunk_id_uuid_update
BEFORE UPDATE OF chunk_id ON knowledge_items
WHEN
    NEW.chunk_id IS NULL
    OR length(NEW.chunk_id) != 36
    OR substr(NEW.chunk_id, 9, 1) != '-'
    OR substr(NEW.chunk_id, 14, 1) != '-'
    OR substr(NEW.chunk_id, 19, 1) != '-'
    OR substr(NEW.chunk_id, 24, 1) != '-'
    OR length(replace(NEW.chunk_id, '-', '')) != 32
    OR lower(NEW.chunk_id) != NEW.chunk_id
    OR replace(NEW.chunk_id, '-', '') GLOB '*[^0-9a-f]*'
BEGIN
    SELECT RAISE(ABORT, 'ck_knowledge_items_chunk_id_uuid');
END;

CREATE TRIGGER ck_relation_edges_edge_id_uuid_insert
BEFORE INSERT ON relation_edges
WHEN
    NEW.edge_id IS NULL
    OR length(NEW.edge_id) != 36
    OR substr(NEW.edge_id, 9, 1) != '-'
    OR substr(NEW.edge_id, 14, 1) != '-'
    OR substr(NEW.edge_id, 19, 1) != '-'
    OR substr(NEW.edge_id, 24, 1) != '-'
    OR length(replace(NEW.edge_id, '-', '')) != 32
    OR lower(NEW.edge_id) != NEW.edge_id
    OR replace(NEW.edge_id, '-', '') GLOB '*[^0-9a-f]*'
BEGIN
    SELECT RAISE(ABORT, 'ck_relation_edges_edge_id_uuid');
END;

CREATE TRIGGER ck_relation_edges_edge_id_uuid_update
BEFORE UPDATE OF edge_id ON relation_edges
WHEN
    NEW.edge_id IS NULL
    OR length(NEW.edge_id) != 36
    OR substr(NEW.edge_id, 9, 1) != '-'
    OR substr(NEW.edge_id, 14, 1) != '-'
    OR substr(NEW.edge_id, 19, 1) != '-'
    OR substr(NEW.edge_id, 24, 1) != '-'
    OR length(replace(NEW.edge_id, '-', '')) != 32
    OR lower(NEW.edge_id) != NEW.edge_id
    OR replace(NEW.edge_id, '-', '') GLOB '*[^0-9a-f]*'
BEGIN
    SELECT RAISE(ABORT, 'ck_relation_edges_edge_id_uuid');
END;

CREATE TRIGGER ck_relation_edges_evidence_chunk_id_uuid_insert
BEFORE INSERT ON relation_edges
WHEN
    NEW.evidence_chunk_id IS NOT NULL
    AND (
        length(NEW.evidence_chunk_id) != 36
        OR substr(NEW.evidence_chunk_id, 9, 1) != '-'
        OR substr(NEW.evidence_chunk_id, 14, 1) != '-'
        OR substr(NEW.evidence_chunk_id, 19, 1) != '-'
        OR substr(NEW.evidence_chunk_id, 24, 1) != '-'
        OR length(replace(NEW.evidence_chunk_id, '-', '')) != 32
        OR lower(NEW.evidence_chunk_id) != NEW.evidence_chunk_id
        OR replace(NEW.evidence_chunk_id, '-', '') GLOB '*[^0-9a-f]*'
    )
BEGIN
    SELECT RAISE(ABORT, 'ck_relation_edges_evidence_chunk_id_uuid');
END;

CREATE TRIGGER ck_relation_edges_evidence_chunk_id_uuid_update
BEFORE UPDATE OF evidence_chunk_id ON relation_edges
WHEN
    NEW.evidence_chunk_id IS NOT NULL
    AND (
        length(NEW.evidence_chunk_id) != 36
        OR substr(NEW.evidence_chunk_id, 9, 1) != '-'
        OR substr(NEW.evidence_chunk_id, 14, 1) != '-'
        OR substr(NEW.evidence_chunk_id, 19, 1) != '-'
        OR substr(NEW.evidence_chunk_id, 24, 1) != '-'
        OR length(replace(NEW.evidence_chunk_id, '-', '')) != 32
        OR lower(NEW.evidence_chunk_id) != NEW.evidence_chunk_id
        OR replace(NEW.evidence_chunk_id, '-', '') GLOB '*[^0-9a-f]*'
    )
BEGIN
    SELECT RAISE(ABORT, 'ck_relation_edges_evidence_chunk_id_uuid');
END;

CREATE TRIGGER ck_memory_items_memory_id_uuid_insert
BEFORE INSERT ON memory_items
WHEN
    NEW.memory_id IS NULL
    OR length(NEW.memory_id) != 36
    OR substr(NEW.memory_id, 9, 1) != '-'
    OR substr(NEW.memory_id, 14, 1) != '-'
    OR substr(NEW.memory_id, 19, 1) != '-'
    OR substr(NEW.memory_id, 24, 1) != '-'
    OR length(replace(NEW.memory_id, '-', '')) != 32
    OR lower(NEW.memory_id) != NEW.memory_id
    OR replace(NEW.memory_id, '-', '') GLOB '*[^0-9a-f]*'
BEGIN
    SELECT RAISE(ABORT, 'ck_memory_items_memory_id_uuid');
END;

CREATE TRIGGER ck_memory_items_memory_id_uuid_update
BEFORE UPDATE OF memory_id ON memory_items
WHEN
    NEW.memory_id IS NULL
    OR length(NEW.memory_id) != 36
    OR substr(NEW.memory_id, 9, 1) != '-'
    OR substr(NEW.memory_id, 14, 1) != '-'
    OR substr(NEW.memory_id, 19, 1) != '-'
    OR substr(NEW.memory_id, 24, 1) != '-'
    OR length(replace(NEW.memory_id, '-', '')) != 32
    OR lower(NEW.memory_id) != NEW.memory_id
    OR replace(NEW.memory_id, '-', '') GLOB '*[^0-9a-f]*'
BEGIN
    SELECT RAISE(ABORT, 'ck_memory_items_memory_id_uuid');
END;

CREATE TRIGGER ck_file_operation_plans_plan_id_uuid_insert
BEFORE INSERT ON file_operation_plans
WHEN
    NEW.plan_id IS NULL
    OR length(NEW.plan_id) != 36
    OR substr(NEW.plan_id, 9, 1) != '-'
    OR substr(NEW.plan_id, 14, 1) != '-'
    OR substr(NEW.plan_id, 19, 1) != '-'
    OR substr(NEW.plan_id, 24, 1) != '-'
    OR length(replace(NEW.plan_id, '-', '')) != 32
    OR lower(NEW.plan_id) != NEW.plan_id
    OR replace(NEW.plan_id, '-', '') GLOB '*[^0-9a-f]*'
BEGIN
    SELECT RAISE(ABORT, 'ck_file_operation_plans_plan_id_uuid');
END;

CREATE TRIGGER ck_file_operation_plans_plan_id_uuid_update
BEFORE UPDATE OF plan_id ON file_operation_plans
WHEN
    NEW.plan_id IS NULL
    OR length(NEW.plan_id) != 36
    OR substr(NEW.plan_id, 9, 1) != '-'
    OR substr(NEW.plan_id, 14, 1) != '-'
    OR substr(NEW.plan_id, 19, 1) != '-'
    OR substr(NEW.plan_id, 24, 1) != '-'
    OR length(replace(NEW.plan_id, '-', '')) != 32
    OR lower(NEW.plan_id) != NEW.plan_id
    OR replace(NEW.plan_id, '-', '') GLOB '*[^0-9a-f]*'
BEGIN
    SELECT RAISE(ABORT, 'ck_file_operation_plans_plan_id_uuid');
END;

CREATE TRIGGER ck_audit_logs_audit_id_uuid_insert
BEFORE INSERT ON audit_logs
WHEN
    NEW.audit_id IS NULL
    OR length(NEW.audit_id) != 36
    OR substr(NEW.audit_id, 9, 1) != '-'
    OR substr(NEW.audit_id, 14, 1) != '-'
    OR substr(NEW.audit_id, 19, 1) != '-'
    OR substr(NEW.audit_id, 24, 1) != '-'
    OR length(replace(NEW.audit_id, '-', '')) != 32
    OR lower(NEW.audit_id) != NEW.audit_id
    OR replace(NEW.audit_id, '-', '') GLOB '*[^0-9a-f]*'
BEGIN
    SELECT RAISE(ABORT, 'ck_audit_logs_audit_id_uuid');
END;

CREATE TRIGGER ck_audit_logs_audit_id_uuid_update
BEFORE UPDATE OF audit_id ON audit_logs
WHEN
    NEW.audit_id IS NULL
    OR length(NEW.audit_id) != 36
    OR substr(NEW.audit_id, 9, 1) != '-'
    OR substr(NEW.audit_id, 14, 1) != '-'
    OR substr(NEW.audit_id, 19, 1) != '-'
    OR substr(NEW.audit_id, 24, 1) != '-'
    OR length(replace(NEW.audit_id, '-', '')) != 32
    OR lower(NEW.audit_id) != NEW.audit_id
    OR replace(NEW.audit_id, '-', '') GLOB '*[^0-9a-f]*'
BEGIN
    SELECT RAISE(ABORT, 'ck_audit_logs_audit_id_uuid');
END;
