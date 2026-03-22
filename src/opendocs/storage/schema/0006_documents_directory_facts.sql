-- Root-cause fix for S4 directory filters:
-- persist normalized directory facts in SQLite instead of deriving them during retrieval.
--
-- Backfill must derive directory facts from the document's own path/relative_path.
-- documents.source_path carries provenance and must not be repurposed as source-root state.

ALTER TABLE documents ADD COLUMN directory_path TEXT NOT NULL DEFAULT '';
ALTER TABLE documents ADD COLUMN relative_directory_path TEXT NOT NULL DEFAULT '';

UPDATE documents
SET relative_directory_path = (
    WITH normalized(rel_path) AS (
        SELECT trim(replace(relative_path, char(92), '/'), '/')
    )
    SELECT CASE
        WHEN rel_path = '' OR instr(rel_path, '/') = 0 THEN ''
        ELSE COALESCE(
            (
                SELECT group_concat(value, '/')
                FROM json_each(
                    '["' || replace(replace(rel_path, '"', '\"'), '/', '","') || '"]'
                )
                WHERE key < (
                    SELECT max(key)
                    FROM json_each(
                        '["' || replace(replace(rel_path, '"', '\"'), '/', '","') || '"]'
                    )
                )
            ),
            ''
        )
    END
    FROM normalized
);

UPDATE documents
SET directory_path = (
    WITH normalized(doc_path, rel_path, rel_dir) AS (
        SELECT
            replace(path, char(92), '/'),
            trim(replace(relative_path, char(92), '/'), '/'),
            relative_directory_path
    )
    SELECT CASE
        WHEN rel_path = '' THEN
            CASE
                WHEN doc_path = '/' THEN '/'
                WHEN doc_path GLOB '[A-Za-z]:/' THEN doc_path
                ELSE rtrim(doc_path, '/')
            END
        ELSE
            CASE
                WHEN substr(
                    doc_path,
                    1,
                    length(doc_path) - CASE
                        WHEN rel_dir = '' THEN length(rel_path)
                        ELSE length(rel_path) - length(rel_dir) - 1
                    END
                ) = '/' THEN '/'
                WHEN substr(
                    doc_path,
                    1,
                    length(doc_path) - CASE
                        WHEN rel_dir = '' THEN length(rel_path)
                        ELSE length(rel_path) - length(rel_dir) - 1
                    END
                ) GLOB '[A-Za-z]:/' THEN substr(
                    doc_path,
                    1,
                    length(doc_path) - CASE
                        WHEN rel_dir = '' THEN length(rel_path)
                        ELSE length(rel_path) - length(rel_dir) - 1
                    END
                )
                ELSE rtrim(substr(
                    doc_path,
                    1,
                    length(doc_path) - CASE
                        WHEN rel_dir = '' THEN length(rel_path)
                        ELSE length(rel_path) - length(rel_dir) - 1
                    END
                ), '/')
            END
    END
    FROM normalized
);

CREATE INDEX idx_documents_directory_path ON documents (directory_path);
CREATE INDEX idx_documents_relative_directory_path ON documents (relative_directory_path);
