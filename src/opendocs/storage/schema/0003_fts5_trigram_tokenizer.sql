-- S4: Migrate FTS5 from unicode61 (default) to trigram tokenizer.
-- ADR-0012: trigram enables 3+ char substring matching for CJK.
-- Structure is identical to 0001 except for tokenize='trigram'.

DROP TRIGGER IF EXISTS chunks_ai;
DROP TRIGGER IF EXISTS chunks_ad;
DROP TRIGGER IF EXISTS chunks_au;
DROP TABLE IF EXISTS chunk_fts;

CREATE VIRTUAL TABLE chunk_fts USING fts5(
    chunk_id UNINDEXED,
    doc_id UNINDEXED,
    text,
    content='chunks',
    content_rowid='rowid',
    tokenize='trigram'
);

CREATE TRIGGER chunks_ai AFTER INSERT ON chunks BEGIN
    INSERT INTO chunk_fts(rowid, chunk_id, doc_id, text)
    VALUES (new.rowid, new.chunk_id, new.doc_id, new.text);
END;

CREATE TRIGGER chunks_ad AFTER DELETE ON chunks BEGIN
    INSERT INTO chunk_fts(chunk_fts, rowid, chunk_id, doc_id, text)
    VALUES ('delete', old.rowid, old.chunk_id, old.doc_id, old.text);
END;

CREATE TRIGGER chunks_au AFTER UPDATE ON chunks BEGIN
    INSERT INTO chunk_fts(chunk_fts, rowid, chunk_id, doc_id, text)
    VALUES ('delete', old.rowid, old.chunk_id, old.doc_id, old.text);
    INSERT INTO chunk_fts(rowid, chunk_id, doc_id, text)
    VALUES (new.rowid, new.chunk_id, new.doc_id, new.text);
END;

-- Backfill: rebuild FTS index from content table (chunks).
-- On empty DB this is a no-op; on S3 DB with data it re-indexes all chunks.
INSERT INTO chunk_fts(chunk_fts) VALUES('rebuild');
