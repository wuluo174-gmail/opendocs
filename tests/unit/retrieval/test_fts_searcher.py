"""Unit tests for FtsSearcher with real in-memory SQLite + trigram."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text as sa_text
from sqlalchemy.orm import Session

from opendocs.retrieval.fts_searcher import FtsSearcher
from opendocs.storage.db import build_sqlite_engine, init_db
from opendocs.utils.path_facts import (
    build_display_path,
    derive_directory_facts,
    derive_source_display_root,
)


@pytest.fixture()
def fts_env(tmp_path):
    """Create a real SQLite DB with trigram FTS + test data."""
    db_path = tmp_path / "fts_test.db"
    init_db(db_path)
    engine = build_sqlite_engine(db_path)

    doc_id = str(uuid.uuid4())
    source_root_id = str(uuid.uuid4())
    chunk_id_1 = str(uuid.uuid4())
    chunk_id_2 = str(uuid.uuid4())

    with Session(engine) as session:
        session.execute(
            sa_text(
                "INSERT INTO source_roots (source_root_id, path, display_root, label, "
                "exclude_rules_json, recursive, is_active, created_at, updated_at) VALUES "
                "(:sid, :path, :display_root, :label, :rules, :recursive, :active, "
                ":created_at, :updated_at)"
            ),
            {
                "sid": source_root_id,
                "path": "/test",
                "display_root": derive_source_display_root("/test", source_root_id=source_root_id),
                "label": "fts fixture",
                "rules": "{}",
                "recursive": 1,
                "active": 1,
                "created_at": "2026-01-01T00:00:00",
                "updated_at": "2026-01-01T00:00:00",
            },
        )
        session.execute(
            sa_text(
                "INSERT INTO documents (doc_id, path, relative_path, display_path, "
                "directory_path, relative_directory_path, source_root_id, source_path, "
                "hash_sha256, title, file_type, size_bytes, created_at, modified_at, "
                "parse_status, tags_json, sensitivity, is_deleted_from_fs) VALUES "
                "(:did, :p, :rp, :display_path, :dp, :rdp, :src, :sp, :h, :t, :ft, :sz, "
                ":ca, :ma, :ps, :tj, :s, :d)"
            ),
            {
                "did": doc_id,
                "p": "/test/doc.md",
                "rp": "doc.md",
                "display_path": build_display_path("test", "doc.md"),
                "dp": derive_directory_facts("/test/doc.md", "doc.md")[0],
                "rdp": derive_directory_facts("/test/doc.md", "doc.md")[1],
                "src": source_root_id,
                "sp": "/test/doc.md",
                "h": "a" * 64,
                "t": "Test Doc",
                "ft": "md",
                "sz": 100,
                "ca": "2026-01-01T00:00:00",
                "ma": "2026-01-01T00:00:00",
                "ps": "success",
                "tj": "[]",
                "s": "internal",
                "d": 0,
            },
        )
        session.execute(
            sa_text(
                "INSERT INTO chunks (chunk_id, doc_id, chunk_index, text, "
                "char_start, char_end) VALUES (:cid, :did, :ci, :txt, :cs, :ce)"
            ),
            {
                "cid": chunk_id_1,
                "did": doc_id,
                "ci": 0,
                "txt": "项目进度报告 AI and machine learning 在文档分类中的应用",
                "cs": 0,
                "ce": 30,
            },
        )
        session.execute(
            sa_text(
                "INSERT INTO chunks (chunk_id, doc_id, chunk_index, text, "
                "char_start, char_end) VALUES (:cid, :did, :ci, :txt, :cs, :ce)"
            ),
            {
                "cid": chunk_id_2,
                "did": doc_id,
                "ci": 1,
                "txt": "Weekly Status Report completed authentication module shared-needle",
                "cs": 31,
                "ce": 80,
            },
        )
        session.commit()

    return engine, doc_id, chunk_id_1, chunk_id_2


class TestFtsSearcherTrigram:
    def test_4char_cjk_match(self, fts_env) -> None:
        engine, doc_id, cid1, _ = fts_env
        searcher = FtsSearcher()
        with Session(engine) as session:
            results = searcher.search(session, "项目进度")
        assert len(results) > 0
        assert any(r[0] == cid1 for r in results)

    def test_english_match(self, fts_env) -> None:
        engine, _, _, cid2 = fts_env
        searcher = FtsSearcher()
        with Session(engine) as session:
            results = searcher.search(session, "authentication")
        assert len(results) > 0
        assert any(r[0] == cid2 for r in results)

    def test_hyphenated_term_matches_without_query_crash(self, fts_env) -> None:
        engine, _, _, cid2 = fts_env
        searcher = FtsSearcher()
        with Session(engine) as session:
            results = searcher.search(session, "shared-needle")
        assert len(results) > 0
        assert any(r[0] == cid2 for r in results)

    def test_2char_cjk_returns_empty(self, fts_env) -> None:
        """Trigram can't match < 3 char terms — expected empty."""
        engine, *_ = fts_env
        searcher = FtsSearcher()
        with Session(engine) as session:
            results = searcher.search(session, "项目")
        assert results == []

    def test_fts_or_operator(self, fts_env) -> None:
        engine, _, cid1, cid2 = fts_env
        searcher = FtsSearcher()
        with Session(engine) as session:
            results = searcher.search(session, "项目进度 OR authentication")
        chunk_ids = {r[0] for r in results}
        # OR should match either chunk
        assert len(chunk_ids) >= 1

    def test_prefilter_doc_ids(self, fts_env) -> None:
        engine, doc_id, *_ = fts_env
        searcher = FtsSearcher()
        fake_id = str(uuid.uuid4())
        with Session(engine) as session:
            results = searcher.search(session, "项目进度", doc_ids={fake_id})
        assert results == []

    def test_nonsense_returns_empty(self, fts_env) -> None:
        engine, *_ = fts_env
        searcher = FtsSearcher()
        with Session(engine) as session:
            results = searcher.search(session, "qxzjkw vbnmrt")
        assert results == []

    def test_missing_fts_table_raises(self, fts_env) -> None:
        engine, *_ = fts_env
        searcher = FtsSearcher()

        with Session(engine) as session:
            session.execute(sa_text("DROP TABLE chunk_fts"))
            session.commit()

        with Session(engine) as session:
            with pytest.raises(Exception, match="no such table: chunk_fts"):
                searcher.search(session, "项目进度")

    def test_malformed_match_expression_returns_empty(self, fts_env) -> None:
        engine, *_ = fts_env
        searcher = FtsSearcher()
        with Session(engine) as session:
            results = searcher.search(session, "项目进度 OR")
        assert results == []
