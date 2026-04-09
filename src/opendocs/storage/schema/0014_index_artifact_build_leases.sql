ALTER TABLE index_artifacts
ADD COLUMN generation INTEGER NOT NULL DEFAULT 0 CHECK (generation >= 0);

UPDATE index_artifacts
SET generation = CASE
    WHEN status = 'ready' THEN 1
    ELSE 0
END
WHERE generation = 0;

ALTER TABLE index_artifacts
ADD COLUMN active_build_token TEXT;

ALTER TABLE index_artifacts
ADD COLUMN build_started_at TEXT;

ALTER TABLE index_artifacts
ADD COLUMN lease_expires_at TEXT;

CREATE UNIQUE INDEX idx_index_artifacts_active_build_token
ON index_artifacts (active_build_token)
WHERE active_build_token IS NOT NULL;
