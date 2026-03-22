"""Generation integration test fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.engine import Engine

from opendocs.app.generation_service import GenerationService
from opendocs.app.index_service import IndexService
from opendocs.app.source_service import SourceService
from opendocs.provider.mock import MockProvider
from opendocs.retrieval.stage_search_corpus import (
    build_s4_search_source_defaults,
    materialize_s4_search_corpus,
)
from opendocs.storage.db import build_sqlite_engine, init_db


@pytest.fixture()
def generation_indexed_env(tmp_path: Path) -> tuple[Engine, Path, Path]:
    """Index corpus and return (engine, hnsw_path, tmp_path)."""
    corpus_dir = tmp_path / "corpus"
    materialize_s4_search_corpus(corpus_dir)
    db_path = tmp_path / "gen_test.db"
    init_db(db_path)
    engine = build_sqlite_engine(db_path)
    hnsw_path = tmp_path / "hnsw" / "gen.hnsw"
    hnsw_path.parent.mkdir(parents=True, exist_ok=True)

    source = SourceService(engine).add_source(
        corpus_dir,
        default_metadata=build_s4_search_source_defaults(),
    )
    IndexService(engine, hnsw_path=hnsw_path).full_index_source(source.source_root_id)

    return engine, hnsw_path, tmp_path


@pytest.fixture()
def generation_service(
    generation_indexed_env: tuple[Engine, Path, Path],
) -> GenerationService:
    engine, hnsw_path, tmp_path = generation_indexed_env
    output_dir = tmp_path / "OpenDocs_Output"
    return GenerationService(
        engine,
        hnsw_path=hnsw_path,
        provider=MockProvider(),
        output_dir=str(output_dir),
    )
