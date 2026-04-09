CREATE TABLE source_roots (
    source_root_id TEXT PRIMARY KEY CHECK (
        length(source_root_id) = 36
        AND substr(source_root_id, 9, 1) = '-'
        AND substr(source_root_id, 14, 1) = '-'
        AND substr(source_root_id, 19, 1) = '-'
        AND substr(source_root_id, 24, 1) = '-'
        AND length(replace(source_root_id, '-', '')) = 32
        AND lower(source_root_id) = source_root_id
        AND NOT replace(source_root_id, '-', '') GLOB '*[^0-9a-f]*'
    ),
    path TEXT NOT NULL UNIQUE,
    display_root TEXT NOT NULL UNIQUE,
    label TEXT,
    exclude_rules_json TEXT NOT NULL DEFAULT '{}',
    recursive INTEGER NOT NULL DEFAULT 1,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE documents (
    doc_id TEXT PRIMARY KEY CHECK (
        length(doc_id) = 36
        AND substr(doc_id, 9, 1) = '-'
        AND substr(doc_id, 14, 1) = '-'
        AND substr(doc_id, 19, 1) = '-'
        AND substr(doc_id, 24, 1) = '-'
        AND length(replace(doc_id, '-', '')) = 32
        AND lower(doc_id) = doc_id
        AND NOT replace(doc_id, '-', '') GLOB '*[^0-9a-f]*'
    ),
    path TEXT NOT NULL UNIQUE,
    relative_path TEXT NOT NULL,
    display_path TEXT NOT NULL,
    source_root_id TEXT NOT NULL CHECK (
        length(source_root_id) = 36
        AND substr(source_root_id, 9, 1) = '-'
        AND substr(source_root_id, 14, 1) = '-'
        AND substr(source_root_id, 19, 1) = '-'
        AND substr(source_root_id, 24, 1) = '-'
        AND length(replace(source_root_id, '-', '')) = 32
        AND lower(source_root_id) = source_root_id
        AND NOT replace(source_root_id, '-', '') GLOB '*[^0-9a-f]*'
    ),
    source_path TEXT NOT NULL,
    hash_sha256 TEXT CHECK (
        hash_sha256 IS NULL
        OR (
            length(hash_sha256) = 64
            AND lower(hash_sha256) = hash_sha256
            AND NOT hash_sha256 GLOB '*[^0-9a-f]*'
        )
    ),
    title TEXT NOT NULL,
    file_type TEXT NOT NULL CHECK (file_type IN ('txt', 'md', 'docx', 'pdf')),
    size_bytes INTEGER NOT NULL CHECK (size_bytes >= 0),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    modified_at TEXT NOT NULL DEFAULT (datetime('now')),
    indexed_at TEXT,
    parse_status TEXT NOT NULL DEFAULT 'success' CHECK (parse_status IN ('success', 'partial', 'failed')),
    category TEXT,
    tags_json TEXT NOT NULL DEFAULT '[]',
    sensitivity TEXT NOT NULL DEFAULT 'internal' CHECK (sensitivity IN ('public', 'internal', 'sensitive')),
    is_deleted_from_fs INTEGER NOT NULL DEFAULT 0,
    CHECK (parse_status = 'failed' OR hash_sha256 IS NOT NULL),
    FOREIGN KEY(source_root_id) REFERENCES source_roots(source_root_id) ON DELETE RESTRICT
);

CREATE INDEX idx_documents_source_root_id ON documents (source_root_id);
CREATE INDEX idx_documents_hash_sha256 ON documents (hash_sha256);

CREATE TABLE chunks (
    chunk_id TEXT PRIMARY KEY CHECK (
        length(chunk_id) = 36
        AND substr(chunk_id, 9, 1) = '-'
        AND substr(chunk_id, 14, 1) = '-'
        AND substr(chunk_id, 19, 1) = '-'
        AND substr(chunk_id, 24, 1) = '-'
        AND length(replace(chunk_id, '-', '')) = 32
        AND lower(chunk_id) = chunk_id
        AND NOT replace(chunk_id, '-', '') GLOB '*[^0-9a-f]*'
    ),
    doc_id TEXT NOT NULL CHECK (
        length(doc_id) = 36
        AND substr(doc_id, 9, 1) = '-'
        AND substr(doc_id, 14, 1) = '-'
        AND substr(doc_id, 19, 1) = '-'
        AND substr(doc_id, 24, 1) = '-'
        AND length(replace(doc_id, '-', '')) = 32
        AND lower(doc_id) = doc_id
        AND NOT replace(doc_id, '-', '') GLOB '*[^0-9a-f]*'
    ),
    chunk_index INTEGER NOT NULL CHECK (chunk_index >= 0),
    text TEXT NOT NULL,
    char_start INTEGER NOT NULL CHECK (char_start >= 0),
    char_end INTEGER NOT NULL CHECK (char_end >= char_start),
    page_no INTEGER CHECK (page_no IS NULL OR page_no >= 1),
    paragraph_start INTEGER CHECK (paragraph_start IS NULL OR paragraph_start >= 0),
    paragraph_end INTEGER CHECK (paragraph_end IS NULL OR paragraph_end >= 0),
    heading_path TEXT,
    token_estimate INTEGER,
    embedding_model TEXT,
    embedding_key TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK (
        paragraph_start IS NULL
        OR paragraph_end IS NULL
        OR paragraph_end >= paragraph_start
    ),
    FOREIGN KEY(doc_id) REFERENCES documents(doc_id) ON DELETE CASCADE,
    UNIQUE(doc_id, chunk_index)
);

CREATE INDEX idx_chunks_doc_id ON chunks (doc_id);
CREATE INDEX idx_chunks_embedding_key ON chunks (embedding_key);

CREATE VIRTUAL TABLE chunk_fts USING fts5(
    chunk_id UNINDEXED,
    doc_id UNINDEXED,
    text,
    content='chunks',
    content_rowid='rowid'
);

CREATE TRIGGER chunks_ai AFTER INSERT ON chunks BEGIN
    INSERT INTO chunk_fts(rowid, chunk_id, doc_id, text)
    VALUES (new.rowid, new.chunk_id, new.doc_id, new.text);
END;

CREATE TRIGGER chunks_ad AFTER DELETE ON chunks BEGIN
    INSERT INTO chunk_fts(chunk_fts, rowid, chunk_id, doc_id, text)
    VALUES ('delete', old.rowid, old.chunk_id, old.doc_id, old.text);
END;

CREATE TRIGGER chunks_au AFTER UPDATE ON chunks BEGIN
    INSERT INTO chunk_fts(chunk_fts, rowid, chunk_id, doc_id, text)
    VALUES ('delete', old.rowid, old.chunk_id, old.doc_id, old.text);
    INSERT INTO chunk_fts(rowid, chunk_id, doc_id, text)
    VALUES (new.rowid, new.chunk_id, new.doc_id, new.text);
END;

CREATE TABLE knowledge_items (
    knowledge_id TEXT PRIMARY KEY CHECK (
        length(knowledge_id) = 36
        AND substr(knowledge_id, 9, 1) = '-'
        AND substr(knowledge_id, 14, 1) = '-'
        AND substr(knowledge_id, 19, 1) = '-'
        AND substr(knowledge_id, 24, 1) = '-'
        AND length(replace(knowledge_id, '-', '')) = 32
        AND lower(knowledge_id) = knowledge_id
        AND NOT replace(knowledge_id, '-', '') GLOB '*[^0-9a-f]*'
    ),
    doc_id TEXT NOT NULL CHECK (
        length(doc_id) = 36
        AND substr(doc_id, 9, 1) = '-'
        AND substr(doc_id, 14, 1) = '-'
        AND substr(doc_id, 19, 1) = '-'
        AND substr(doc_id, 24, 1) = '-'
        AND length(replace(doc_id, '-', '')) = 32
        AND lower(doc_id) = doc_id
        AND NOT replace(doc_id, '-', '') GLOB '*[^0-9a-f]*'
    ),
    chunk_id TEXT NOT NULL CHECK (
        length(chunk_id) = 36
        AND substr(chunk_id, 9, 1) = '-'
        AND substr(chunk_id, 14, 1) = '-'
        AND substr(chunk_id, 19, 1) = '-'
        AND substr(chunk_id, 24, 1) = '-'
        AND length(replace(chunk_id, '-', '')) = 32
        AND lower(chunk_id) = chunk_id
        AND NOT replace(chunk_id, '-', '') GLOB '*[^0-9a-f]*'
    ),
    summary TEXT NOT NULL,
    entities_json TEXT NOT NULL DEFAULT '[]',
    topics_json TEXT NOT NULL DEFAULT '[]',
    confidence REAL NOT NULL CHECK (confidence >= 0.0 AND confidence <= 1.0),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(doc_id) REFERENCES documents(doc_id) ON DELETE CASCADE,
    FOREIGN KEY(chunk_id) REFERENCES chunks(chunk_id) ON DELETE CASCADE
);

CREATE INDEX idx_knowledge_items_doc_id ON knowledge_items (doc_id);
CREATE INDEX idx_knowledge_items_chunk_id ON knowledge_items (chunk_id);

CREATE TABLE relation_edges (
    edge_id TEXT PRIMARY KEY CHECK (
        length(edge_id) = 36
        AND substr(edge_id, 9, 1) = '-'
        AND substr(edge_id, 14, 1) = '-'
        AND substr(edge_id, 19, 1) = '-'
        AND substr(edge_id, 24, 1) = '-'
        AND length(replace(edge_id, '-', '')) = 32
        AND lower(edge_id) = edge_id
        AND NOT replace(edge_id, '-', '') GLOB '*[^0-9a-f]*'
    ),
    src_type TEXT NOT NULL CHECK (
        src_type IN ('document', 'chunk', 'knowledge', 'memory', 'entity', 'topic')
    ),
    src_id TEXT NOT NULL,
    dst_type TEXT NOT NULL CHECK (
        dst_type IN ('document', 'chunk', 'knowledge', 'memory', 'entity', 'topic')
    ),
    dst_id TEXT NOT NULL,
    relation_type TEXT NOT NULL CHECK (
        relation_type IN ('related_to', 'mentions', 'derived_from', 'same_project')
    ),
    weight REAL NOT NULL DEFAULT 1.0 CHECK (weight >= 0.0),
    evidence_chunk_id TEXT CHECK (
        evidence_chunk_id IS NULL
        OR (
            length(evidence_chunk_id) = 36
            AND substr(evidence_chunk_id, 9, 1) = '-'
            AND substr(evidence_chunk_id, 14, 1) = '-'
            AND substr(evidence_chunk_id, 19, 1) = '-'
            AND substr(evidence_chunk_id, 24, 1) = '-'
            AND length(replace(evidence_chunk_id, '-', '')) = 32
            AND lower(evidence_chunk_id) = evidence_chunk_id
            AND NOT replace(evidence_chunk_id, '-', '') GLOB '*[^0-9a-f]*'
        )
    ),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(evidence_chunk_id) REFERENCES chunks(chunk_id) ON DELETE SET NULL
);

CREATE INDEX idx_relation_edges_src ON relation_edges (src_type, src_id);
CREATE INDEX idx_relation_edges_dst ON relation_edges (dst_type, dst_id);
CREATE INDEX idx_relation_edges_evidence_chunk_id ON relation_edges (evidence_chunk_id);

CREATE TABLE memory_items (
    memory_id TEXT PRIMARY KEY CHECK (
        length(memory_id) = 36
        AND substr(memory_id, 9, 1) = '-'
        AND substr(memory_id, 14, 1) = '-'
        AND substr(memory_id, 19, 1) = '-'
        AND substr(memory_id, 24, 1) = '-'
        AND length(replace(memory_id, '-', '')) = 32
        AND lower(memory_id) = memory_id
        AND NOT replace(memory_id, '-', '') GLOB '*[^0-9a-f]*'
    ),
    memory_type TEXT NOT NULL CHECK (memory_type IN ('M1', 'M2')),
    memory_kind TEXT NOT NULL CHECK (
        memory_kind IN ('task_snapshot', 'retry_point', 'preference_pattern', 'workflow_hint')
    ),
    scope_type TEXT NOT NULL CHECK (scope_type IN ('task', 'user')),
    scope_id TEXT NOT NULL,
    key TEXT NOT NULL,
    content TEXT NOT NULL,
    source_event_ids_json TEXT NOT NULL DEFAULT '[]',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    importance REAL NOT NULL DEFAULT 0.5 CHECK (importance >= 0.0 AND importance <= 1.0),
    confidence REAL NOT NULL DEFAULT 1.0 CHECK (confidence >= 0.0 AND confidence <= 1.0),
    status TEXT NOT NULL DEFAULT 'active' CHECK (
        status IN ('active', 'expired', 'disabled', 'superseded')
    ),
    review_window_days INTEGER NOT NULL DEFAULT 30 CHECK (review_window_days >= 0),
    user_confirmed_count INTEGER NOT NULL DEFAULT 0 CHECK (user_confirmed_count >= 0),
    last_user_confirmed_at TEXT,
    recall_count INTEGER NOT NULL DEFAULT 0 CHECK (recall_count >= 0),
    last_recalled_at TEXT,
    decay_score REAL NOT NULL DEFAULT 0.0 CHECK (decay_score >= 0.0 AND decay_score <= 1.0),
    promotion_state TEXT NOT NULL DEFAULT 'promoted' CHECK (
        promotion_state IN ('candidate', 'promoted')
    ),
    consolidated_from_json TEXT NOT NULL DEFAULT '[]',
    supersedes_memory_id TEXT CHECK (
        supersedes_memory_id IS NULL
        OR (
            length(supersedes_memory_id) = 36
            AND substr(supersedes_memory_id, 9, 1) = '-'
            AND substr(supersedes_memory_id, 14, 1) = '-'
            AND substr(supersedes_memory_id, 19, 1) = '-'
            AND substr(supersedes_memory_id, 24, 1) = '-'
            AND length(replace(supersedes_memory_id, '-', '')) = 32
            AND lower(supersedes_memory_id) = supersedes_memory_id
            AND NOT replace(supersedes_memory_id, '-', '') GLOB '*[^0-9a-f]*'
        )
    ),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(supersedes_memory_id) REFERENCES memory_items(memory_id) ON DELETE SET NULL
);

CREATE UNIQUE INDEX idx_memory_items_active_scope_key
    ON memory_items (memory_type, scope_type, scope_id, key)
    WHERE status = 'active' AND promotion_state = 'promoted';
CREATE INDEX idx_memory_items_scope ON memory_items (scope_type, scope_id);
CREATE INDEX idx_memory_items_supersedes_memory ON memory_items (supersedes_memory_id);

CREATE TABLE file_operation_plans (
    plan_id TEXT PRIMARY KEY CHECK (
        length(plan_id) = 36
        AND substr(plan_id, 9, 1) = '-'
        AND substr(plan_id, 14, 1) = '-'
        AND substr(plan_id, 19, 1) = '-'
        AND substr(plan_id, 24, 1) = '-'
        AND length(replace(plan_id, '-', '')) = 32
        AND lower(plan_id) = plan_id
        AND NOT replace(plan_id, '-', '') GLOB '*[^0-9a-f]*'
    ),
    operation_type TEXT NOT NULL CHECK (operation_type IN ('move', 'rename', 'create')),
    status TEXT NOT NULL DEFAULT 'draft' CHECK (
        status IN ('draft', 'approved', 'executed', 'rolled_back', 'failed')
    ),
    item_count INTEGER NOT NULL DEFAULT 0 CHECK (item_count >= 0),
    risk_level TEXT NOT NULL DEFAULT 'low' CHECK (risk_level IN ('low', 'medium', 'high')),
    preview_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    approved_at TEXT,
    executed_at TEXT
);

CREATE TABLE task_events (
    event_id TEXT PRIMARY KEY CHECK (
        length(event_id) = 36
        AND substr(event_id, 9, 1) = '-'
        AND substr(event_id, 14, 1) = '-'
        AND substr(event_id, 19, 1) = '-'
        AND substr(event_id, 24, 1) = '-'
        AND length(replace(event_id, '-', '')) = 32
        AND lower(event_id) = event_id
        AND NOT replace(event_id, '-', '') GLOB '*[^0-9a-f]*'
    ),
    trace_id TEXT NOT NULL CHECK (length(trace_id) > 0),
    stage_id TEXT NOT NULL CHECK (length(stage_id) > 0),
    task_type TEXT NOT NULL CHECK (length(task_type) > 0),
    scope_type TEXT NOT NULL CHECK (scope_type IN ('session', 'task', 'user')),
    scope_id TEXT NOT NULL CHECK (length(scope_id) > 0),
    input_summary TEXT NOT NULL,
    output_summary TEXT NOT NULL,
    related_chunk_ids_json TEXT NOT NULL DEFAULT '[]',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    related_plan_id TEXT CHECK (
        related_plan_id IS NULL
        OR (
            length(related_plan_id) = 36
            AND substr(related_plan_id, 9, 1) = '-'
            AND substr(related_plan_id, 14, 1) = '-'
            AND substr(related_plan_id, 19, 1) = '-'
            AND substr(related_plan_id, 24, 1) = '-'
            AND length(replace(related_plan_id, '-', '')) = 32
            AND lower(related_plan_id) = related_plan_id
            AND NOT replace(related_plan_id, '-', '') GLOB '*[^0-9a-f]*'
        )
    ),
    artifact_ref TEXT,
    occurred_at TEXT NOT NULL DEFAULT (datetime('now')),
    persisted_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(related_plan_id) REFERENCES file_operation_plans(plan_id) ON DELETE RESTRICT
);

CREATE INDEX idx_task_events_trace ON task_events (trace_id);
CREATE INDEX idx_task_events_scope ON task_events (scope_type, scope_id);
CREATE INDEX idx_task_events_occurred_at ON task_events (occurred_at);
CREATE INDEX idx_task_events_related_plan ON task_events (related_plan_id);

CREATE TABLE audit_logs (
    audit_id TEXT PRIMARY KEY CHECK (
        length(audit_id) = 36
        AND substr(audit_id, 9, 1) = '-'
        AND substr(audit_id, 14, 1) = '-'
        AND substr(audit_id, 19, 1) = '-'
        AND substr(audit_id, 24, 1) = '-'
        AND length(replace(audit_id, '-', '')) = 32
        AND lower(audit_id) = audit_id
        AND NOT replace(audit_id, '-', '') GLOB '*[^0-9a-f]*'
    ),
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    actor TEXT NOT NULL CHECK (actor IN ('user', 'system', 'model')),
    operation TEXT NOT NULL,
    target_type TEXT NOT NULL CHECK (
        target_type IN (
            'document', 'plan', 'memory', 'task_event', 'answer',
            'source', 'search', 'provider_call',
            'generation', 'index_run', 'rollback', 'artifact'
        )
    ),
    target_id TEXT NOT NULL,
    result TEXT NOT NULL CHECK (result IN ('success', 'failure')),
    detail_json TEXT NOT NULL DEFAULT '{}',
    trace_id TEXT NOT NULL CHECK (length(trace_id) > 0)
);

CREATE INDEX idx_audit_logs_timestamp ON audit_logs (timestamp);
CREATE INDEX idx_audit_logs_trace_id ON audit_logs (trace_id);
CREATE INDEX idx_audit_logs_target ON audit_logs (target_type, target_id);
CREATE INDEX idx_audit_logs_operation ON audit_logs (operation);
