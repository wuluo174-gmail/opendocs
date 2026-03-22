-- Persist source-level default metadata so S4 filters have an upstream owner.

ALTER TABLE source_roots ADD COLUMN default_category TEXT;

ALTER TABLE source_roots ADD COLUMN default_tags_json TEXT NOT NULL DEFAULT '[]';

ALTER TABLE source_roots ADD COLUMN default_sensitivity TEXT
    CHECK (default_sensitivity IS NULL OR default_sensitivity IN ('public', 'internal', 'sensitive'));
