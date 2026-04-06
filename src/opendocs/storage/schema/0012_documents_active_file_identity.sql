-- file_identity identifies the current active file lineage, not every
-- historical document row forever. Deleted lineages must keep their
-- provenance without blocking a new active document that reuses the same
-- filesystem identity.

DROP INDEX IF EXISTS idx_documents_file_identity;

CREATE UNIQUE INDEX idx_documents_file_identity
    ON documents (file_identity)
    WHERE file_identity IS NOT NULL AND is_deleted_from_fs = 0;
