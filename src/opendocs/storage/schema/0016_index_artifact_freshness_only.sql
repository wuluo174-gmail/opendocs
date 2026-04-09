PRAGMA foreign_keys = OFF;

ALTER TABLE index_artifacts RENAME TO index_artifacts_legacy;
ALTER TABLE index_artifact_generations RENAME TO index_artifact_generations_legacy;

CREATE TABLE index_artifacts (
    artifact_name TEXT PRIMARY KEY CHECK (
        artifact_name IN ('dense_hnsw')
    ),
    status TEXT NOT NULL DEFAULT 'stale' CHECK (
        status IN ('stale', 'ready', 'failed')
    ),
    artifact_path TEXT NOT NULL,
    embedder_model TEXT NOT NULL,
    embedder_dim INTEGER NOT NULL CHECK (embedder_dim > 0),
    embedder_signature TEXT NOT NULL,
    generation INTEGER NOT NULL DEFAULT 0 CHECK (generation >= 0),
    active_build_token TEXT,
    build_started_at TEXT,
    lease_expires_at TEXT,
    last_error TEXT,
    last_reason TEXT,
    last_built_at TEXT,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE index_artifact_generations (
    artifact_name TEXT NOT NULL,
    generation INTEGER NOT NULL CHECK (generation > 0),
    bundle_path TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('committed', 'retained', 'deleted')),
    committed_at TEXT NOT NULL,
    retired_at TEXT,
    delete_after TEXT,
    deleted_at TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (artifact_name, generation),
    FOREIGN KEY (artifact_name) REFERENCES index_artifacts(artifact_name) ON DELETE CASCADE
);

INSERT INTO index_artifacts (
    artifact_name,
    status,
    artifact_path,
    embedder_model,
    embedder_dim,
    embedder_signature,
    generation,
    active_build_token,
    build_started_at,
    lease_expires_at,
    last_error,
    last_reason,
    last_built_at,
    updated_at
)
SELECT
    artifact_name,
    CASE
        WHEN status = 'building' THEN 'stale'
        ELSE status
    END,
    artifact_path,
    embedder_model,
    embedder_dim,
    embedder_signature,
    generation,
    active_build_token,
    build_started_at,
    lease_expires_at,
    last_error,
    CASE
        WHEN status = 'building' AND COALESCE(last_reason, '') = '' THEN 'legacy_building_status'
        ELSE last_reason
    END,
    last_built_at,
    updated_at
FROM index_artifacts_legacy;

INSERT INTO index_artifact_generations (
    artifact_name,
    generation,
    bundle_path,
    state,
    committed_at,
    retired_at,
    delete_after,
    deleted_at,
    updated_at
)
SELECT
    artifact_name,
    generation,
    bundle_path,
    state,
    committed_at,
    retired_at,
    delete_after,
    deleted_at,
    updated_at
FROM index_artifact_generations_legacy;

DROP TABLE index_artifact_generations_legacy;
DROP TABLE index_artifacts_legacy;

CREATE UNIQUE INDEX idx_index_artifacts_active_build_token
ON index_artifacts (active_build_token)
WHERE active_build_token IS NOT NULL;

CREATE UNIQUE INDEX idx_index_artifact_generations_committed
ON index_artifact_generations (artifact_name)
WHERE state = 'committed';

CREATE INDEX idx_index_artifact_generations_gc_due
ON index_artifact_generations (state, delete_after)
WHERE state = 'retained' AND delete_after IS NOT NULL;

PRAGMA foreign_keys = ON;
