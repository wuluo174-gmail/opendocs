-- Replace timestamp-based source config invalidation with explicit revision tracking.

ALTER TABLE source_roots ADD COLUMN source_config_rev INTEGER NOT NULL DEFAULT 1
    CHECK (source_config_rev >= 1);

ALTER TABLE documents ADD COLUMN source_config_rev INTEGER NOT NULL DEFAULT 1
    CHECK (source_config_rev >= 1);
