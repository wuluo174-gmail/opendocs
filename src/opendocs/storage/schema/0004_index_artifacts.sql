CREATE TABLE index_artifacts (
    artifact_name TEXT PRIMARY KEY CHECK (
        artifact_name IN ('dense_hnsw')
    ),
    status TEXT NOT NULL DEFAULT 'stale' CHECK (
        status IN ('stale', 'ready', 'building', 'failed')
    ),
    artifact_path TEXT NOT NULL,
    embedder_model TEXT NOT NULL,
    embedder_dim INTEGER NOT NULL CHECK (embedder_dim > 0),
    embedder_signature TEXT NOT NULL,
    last_error TEXT,
    last_reason TEXT,
    last_built_at TEXT,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
