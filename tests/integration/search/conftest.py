"""Shared fixtures for S4 search integration tests.

Self-generates a Chinese + English corpus in tmp_path, indexes it,
and provides a SearchService for testing.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.engine import Engine

from opendocs.app.index_service import IndexService
from opendocs.app.search_service import SearchService
from opendocs.app.source_service import SourceService
from opendocs.retrieval.stage_search_corpus import (
    build_s4_search_source_defaults,
    materialize_s4_search_corpus,
)
from opendocs.storage.db import build_sqlite_engine, init_db


@pytest.fixture()
def search_corpus(tmp_path: Path) -> Path:
    """Create a temporary corpus with Chinese + English documents."""
    corpus_dir = tmp_path / "corpus"
    return materialize_s4_search_corpus(corpus_dir)


@pytest.fixture()
def search_db(tmp_path: Path) -> Path:
    """Path for the search test database."""
    return tmp_path / "search_test.db"


@pytest.fixture()
def indexed_search_env(
    search_corpus: Path, search_db: Path, tmp_path: Path
) -> tuple[Engine, Path, Path]:
    """Index the test corpus and return (engine, db_path, hnsw_path)."""
    init_db(search_db)
    engine = build_sqlite_engine(search_db)
    hnsw_path = tmp_path / "hnsw" / "test.hnsw"
    hnsw_path.parent.mkdir(parents=True, exist_ok=True)

    source = SourceService(engine).add_source(
        search_corpus,
        default_metadata=build_s4_search_source_defaults(),
    )
    IndexService(engine, hnsw_path=hnsw_path).full_index_source(source.source_root_id)

    return engine, search_db, hnsw_path


@pytest.fixture()
def search_service(indexed_search_env: tuple[Engine, Path, Path]) -> SearchService:
    """Provide a SearchService with indexed test corpus."""
    engine, _, hnsw_path = indexed_search_env
    return SearchService(engine, hnsw_path=hnsw_path)
