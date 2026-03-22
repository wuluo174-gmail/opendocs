"""End-to-end desktop demo: real DB + fixture corpus → full UI walkthrough."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy.engine import Engine

from opendocs.app.index_service import IndexService
from opendocs.app.source_service import SourceService
from opendocs.config.settings import OpenDocsSettings
from opendocs.retrieval.stage_search_corpus import (
    build_s4_search_source_defaults,
    materialize_s4_search_corpus,
)
from opendocs.storage.db import build_sqlite_engine, init_db
from opendocs.ui.main_window import MainWindow


@pytest.fixture()
def demo_env(tmp_path: Path) -> tuple[Engine, Path]:
    """Set up a real indexed environment for the demo."""
    corpus = materialize_s4_search_corpus(tmp_path / "corpus")
    db_path = tmp_path / "demo.db"
    hnsw_path = tmp_path / "hnsw" / "demo.hnsw"
    hnsw_path.parent.mkdir(parents=True, exist_ok=True)

    init_db(db_path)
    engine = build_sqlite_engine(db_path)

    source = SourceService(engine).add_source(
        corpus, default_metadata=build_s4_search_source_defaults(),
    )
    IndexService(engine, hnsw_path=hnsw_path).full_index_source(source.source_root_id)

    return engine, hnsw_path


def test_full_demo_walkthrough(qtbot, demo_env):
    """Verify the MainWindow can be created with a real indexed DB and navigated."""
    engine, hnsw_path = demo_env

    win = MainWindow(engine, hnsw_path=hnsw_path)
    qtbot.addWidget(win)

    # Sources exist → nav not hidden, starts on search page
    assert not win.nav.isHidden()
    assert win.pages.currentWidget() is win.search_qa_page

    # Search works
    win.search_qa_page.query_input.setText("project")
    win.search_qa_page.search_button.click()
    assert win.search_qa_page.results_list.count() > 0

    # QA works
    win.search_qa_page.query_input.setText("project status")
    win.search_qa_page.ask_button.click()
    assert win.search_qa_page.qa_status_label.text() != ""

    # Navigate to all pages
    for i in range(6):
        win.nav.setCurrentRow(i)
        assert win.pages.currentIndex() == i

    # Generation page loads templates
    assert win.generation_page.template_combo.count() >= 1
