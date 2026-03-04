CREATE TABLE documents (
    doc_id TEXT PRIMARY KEY,
    path TEXT NOT NULL UNIQUE,
    relative_path TEXT NOT NULL,
    source_root_id TEXT NOT NULL,
    source_path TEXT NOT NULL,
    hash_sha256 TEXT NOT NULL,
    title TEXT NOT NULL,
    file_type TEXT NOT NULL CHECK (file_type IN ('txt', 'md', 'docx', 'pdf')),
    size_bytes INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    modified_at TEXT NOT NULL,
    indexed_at TEXT,
    parse_status TEXT NOT NULL CHECK (parse_status IN ('success', 'partial', 'failed')),
    category TEXT,
    tags_json TEXT NOT NULL DEFAULT '[]',
    sensitivity TEXT NOT NULL CHECK (sensitivity IN ('public', 'internal', 'sensitive')),
    is_deleted_from_fs INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX idx_documents_source_root_id ON documents (source_root_id);
CREATE INDEX idx_documents_hash_sha256 ON documents (hash_sha256);

CREATE TABLE chunks (
    chunk_id TEXT PRIMARY KEY,
    doc_id TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    text TEXT NOT NULL,
    char_start INTEGER NOT NULL,
    char_end INTEGER NOT NULL CHECK (char_end >= char_start),
    page_no INTEGER,
    paragraph_start INTEGER,
    paragraph_end INTEGER,
    heading_path TEXT,
    token_estimate INTEGER,
    embedding_model TEXT,
    embedding_key TEXT,
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
    knowledge_id TEXT PRIMARY KEY,
    doc_id TEXT NOT NULL,
    chunk_id TEXT NOT NULL,
    summary TEXT NOT NULL,
    entities_json TEXT NOT NULL DEFAULT '[]',
    topics_json TEXT NOT NULL DEFAULT '[]',
    confidence REAL NOT NULL,
    FOREIGN KEY(doc_id) REFERENCES documents(doc_id) ON DELETE CASCADE,
    FOREIGN KEY(chunk_id) REFERENCES chunks(chunk_id) ON DELETE CASCADE
);

CREATE INDEX idx_knowledge_items_doc_id ON knowledge_items (doc_id);
CREATE INDEX idx_knowledge_items_chunk_id ON knowledge_items (chunk_id);

CREATE TABLE relation_edges (
    edge_id TEXT PRIMARY KEY,
    src_type TEXT NOT NULL,
    src_id TEXT NOT NULL,
    dst_type TEXT NOT NULL,
    dst_id TEXT NOT NULL,
    relation_type TEXT NOT NULL CHECK (
        relation_type IN ('related_to', 'mentions', 'derived_from', 'same_project')
    ),
    weight REAL NOT NULL,
    evidence_chunk_id TEXT,
    FOREIGN KEY(evidence_chunk_id) REFERENCES chunks(chunk_id) ON DELETE SET NULL
);

CREATE INDEX idx_relation_edges_evidence_chunk_id ON relation_edges (evidence_chunk_id);

CREATE TABLE memory_items (
    memory_id TEXT PRIMARY KEY,
    memory_type TEXT NOT NULL CHECK (memory_type IN ('M0', 'M1', 'M2')),
    scope_type TEXT NOT NULL CHECK (scope_type IN ('session', 'task', 'user')),
    scope_id TEXT NOT NULL,
    key TEXT NOT NULL,
    content TEXT NOT NULL,
    importance REAL NOT NULL DEFAULT 0.5,
    status TEXT NOT NULL CHECK (status IN ('active', 'expired', 'disabled')),
    ttl_days INTEGER CHECK (ttl_days IS NULL OR ttl_days >= 0),
    confirmed_count INTEGER NOT NULL DEFAULT 0,
    last_confirmed_at TEXT,
    updated_at TEXT NOT NULL,
    UNIQUE(memory_type, scope_type, scope_id, key)
);

CREATE TABLE file_operation_plans (
    plan_id TEXT PRIMARY KEY,
    operation_type TEXT NOT NULL CHECK (operation_type IN ('move', 'rename', 'create')),
    status TEXT NOT NULL CHECK (
        status IN ('draft', 'approved', 'executed', 'rolled_back', 'failed')
    ),
    item_count INTEGER NOT NULL DEFAULT 0 CHECK (item_count >= 0),
    risk_level TEXT NOT NULL CHECK (risk_level IN ('low', 'medium', 'high')),
    preview_json TEXT NOT NULL DEFAULT '{}',
    approved_at TEXT,
    executed_at TEXT
);

CREATE TABLE audit_logs (
    audit_id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    actor TEXT NOT NULL CHECK (actor IN ('user', 'system', 'model')),
    operation TEXT NOT NULL,
    target_type TEXT NOT NULL CHECK (target_type IN ('document', 'plan', 'memory', 'answer')),
    target_id TEXT NOT NULL,
    result TEXT NOT NULL CHECK (result IN ('success', 'failure')),
    detail_json TEXT NOT NULL DEFAULT '{}',
    trace_id TEXT NOT NULL
);

CREATE INDEX idx_audit_logs_timestamp ON audit_logs (timestamp);
CREATE INDEX idx_audit_logs_trace_id ON audit_logs (trace_id);
CREATE INDEX idx_audit_logs_target ON audit_logs (target_type, target_id);
