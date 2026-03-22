-- Document identity is no longer the current path.
-- Keep path unique only among active documents so a deleted/replaced lineage
-- can retain its historical path while a new active document reuses it.

CREATE TABLE documents_v2 (
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
    path TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    directory_path TEXT NOT NULL,
    relative_directory_path TEXT NOT NULL,
    file_identity TEXT,
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

INSERT INTO documents_v2 (
    doc_id,
    path,
    relative_path,
    directory_path,
    relative_directory_path,
    file_identity,
    source_root_id,
    source_path,
    hash_sha256,
    title,
    file_type,
    size_bytes,
    created_at,
    modified_at,
    indexed_at,
    parse_status,
    category,
    tags_json,
    sensitivity,
    is_deleted_from_fs
)
SELECT
    doc_id,
    path,
    relative_path,
    directory_path,
    relative_directory_path,
    file_identity,
    source_root_id,
    source_path,
    hash_sha256,
    title,
    file_type,
    size_bytes,
    created_at,
    modified_at,
    indexed_at,
    parse_status,
    category,
    tags_json,
    sensitivity,
    is_deleted_from_fs
FROM documents;

DROP TABLE documents;
ALTER TABLE documents_v2 RENAME TO documents;

CREATE INDEX idx_documents_path ON documents (path);
CREATE UNIQUE INDEX idx_documents_active_path
    ON documents (path)
    WHERE is_deleted_from_fs = 0;
CREATE INDEX idx_documents_source_root_id ON documents (source_root_id);
CREATE INDEX idx_documents_hash_sha256 ON documents (hash_sha256);
CREATE INDEX idx_documents_directory_path ON documents (directory_path);
CREATE INDEX idx_documents_relative_directory_path ON documents (relative_directory_path);
CREATE UNIQUE INDEX idx_documents_file_identity ON documents (file_identity);
