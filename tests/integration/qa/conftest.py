"""QA integration test fixtures — extends search conftest with MockProvider."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.engine import Engine

from opendocs.app.index_service import IndexService
from opendocs.app.qa_service import QAService
from opendocs.app.search_service import SearchService
from opendocs.app.source_service import SourceService
from opendocs.provider.mock import MockProvider
from opendocs.retrieval.stage_search_corpus import (
    build_s4_search_source_defaults,
    materialize_s4_search_corpus,
)
from opendocs.storage.db import build_sqlite_engine, init_db


def _write_conflict_docs(corpus_dir: Path) -> None:
    """Add two documents with contradictory facts for conflict testing."""
    doc_a = corpus_dir / "conflict_budget_v1.md"
    doc_a.write_text(
        "# 预算报告 V1\n\n项目预算100万元。交付日期为6月30日。\n",
        encoding="utf-8",
    )
    doc_b = corpus_dir / "conflict_budget_v2.md"
    doc_b.write_text(
        "# 预算报告 V2\n\n项目预算200万元。交付日期为9月30日。\n",
        encoding="utf-8",
    )


def _build_indexed_env(
    tmp_path: Path,
    corpus_dir: Path,
    prefix: str,
) -> tuple[Engine, Path]:
    db_path = tmp_path / f"{prefix}.db"
    init_db(db_path)
    engine = build_sqlite_engine(db_path)
    hnsw_path = tmp_path / "hnsw" / f"{prefix}.hnsw"
    hnsw_path.parent.mkdir(parents=True, exist_ok=True)

    source = SourceService(engine).add_source(
        corpus_dir,
        default_metadata=build_s4_search_source_defaults(),
    )
    IndexService(engine, hnsw_path=hnsw_path).full_index_source(source.source_root_id)
    return engine, hnsw_path


# --- Fixtures for TC-006/007: standard corpus (no conflict docs) ---

@pytest.fixture()
def qa_indexed_env(tmp_path: Path) -> tuple[Engine, Path]:
    """Index standard corpus (no conflict docs)."""
    corpus_dir = tmp_path / "corpus"
    materialize_s4_search_corpus(corpus_dir)
    return _build_indexed_env(tmp_path, corpus_dir, "qa_standard")


@pytest.fixture()
def qa_hnsw_path(qa_indexed_env: tuple[Engine, Path]) -> Path:
    _, hnsw_path = qa_indexed_env
    return hnsw_path


@pytest.fixture()
def qa_service(qa_indexed_env: tuple[Engine, Path]) -> QAService:
    """QAService on standard corpus — no conflict docs."""
    engine, hnsw_path = qa_indexed_env
    return QAService(
        engine,
        hnsw_path=hnsw_path,
        provider=MockProvider(),
        min_evidence=1,
        min_score=0.10,
    )


# --- Fixtures for TC-008: corpus WITH conflict docs ---

@pytest.fixture()
def conflict_indexed_env(tmp_path: Path) -> tuple[Engine, Path]:
    """Index corpus with conflict documents added."""
    corpus_dir = tmp_path / "corpus_conflict"
    materialize_s4_search_corpus(corpus_dir)
    _write_conflict_docs(corpus_dir)
    return _build_indexed_env(tmp_path, corpus_dir, "qa_conflict")


@pytest.fixture()
def conflict_qa_service(conflict_indexed_env: tuple[Engine, Path]) -> QAService:
    """QAService on corpus WITH conflict docs."""
    engine, hnsw_path = conflict_indexed_env
    return QAService(
        engine,
        hnsw_path=hnsw_path,
        provider=MockProvider(),
        min_evidence=1,
        min_score=0.10,
    )
