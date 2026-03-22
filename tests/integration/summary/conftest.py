"""Summary integration test fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.engine import Engine

from opendocs.app.index_service import IndexService
from opendocs.app.source_service import SourceService
from opendocs.app.summary_service import SummaryService
from opendocs.provider.mock import MockProvider
from opendocs.retrieval.stage_search_corpus import (
    build_s4_search_source_defaults,
    materialize_s4_search_corpus,
)
from opendocs.storage.db import build_sqlite_engine, init_db


@pytest.fixture()
def summary_indexed_env(tmp_path: Path) -> tuple[Engine, Path]:
    """Index corpus and return (engine, hnsw_path)."""
    corpus_dir = tmp_path / "corpus"
    materialize_s4_search_corpus(corpus_dir)
    db_path = tmp_path / "summary_test.db"
    init_db(db_path)
    engine = build_sqlite_engine(db_path)
    hnsw_path = tmp_path / "hnsw" / "summary.hnsw"
    hnsw_path.parent.mkdir(parents=True, exist_ok=True)

    source = SourceService(engine).add_source(
        corpus_dir,
        default_metadata=build_s4_search_source_defaults(),
    )
    IndexService(engine, hnsw_path=hnsw_path).full_index_source(source.source_root_id)

    return engine, hnsw_path


@pytest.fixture()
def summary_service(summary_indexed_env: tuple[Engine, Path]) -> SummaryService:
    engine, hnsw_path = summary_indexed_env
    return SummaryService(
        engine,
        hnsw_path=hnsw_path,
        provider=MockProvider(),
    )
