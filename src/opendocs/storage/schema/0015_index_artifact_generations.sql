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

CREATE UNIQUE INDEX idx_index_artifact_generations_committed
ON index_artifact_generations (artifact_name)
WHERE state = 'committed';

CREATE INDEX idx_index_artifact_generations_gc_due
ON index_artifact_generations (state, delete_after)
WHERE state = 'retained' AND delete_after IS NOT NULL;

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
    artifact_path,
    'committed',
    COALESCE(last_built_at, updated_at, CURRENT_TIMESTAMP),
    NULL,
    NULL,
    NULL,
    COALESCE(updated_at, CURRENT_TIMESTAMP)
FROM index_artifacts
WHERE generation > 0;
