-- Decouple document identity from current path.
-- file_identity stores a best-effort filesystem-stable identifier so
-- rename/move reconciliation can update the existing document row instead
-- of creating a new provenance record.

ALTER TABLE documents ADD COLUMN file_identity TEXT;

CREATE UNIQUE INDEX idx_documents_file_identity ON documents (file_identity);
