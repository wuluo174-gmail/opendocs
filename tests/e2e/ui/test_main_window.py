"""MainWindow navigation and wizard-mode tests."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from opendocs.config.settings import OpenDocsSettings
from opendocs.ui.main_window import MainWindow


@pytest.fixture()
def _patch_services():
    """Patch all service constructors to return mocks."""
    targets = [
        "opendocs.ui.main_window.SourceService",
        "opendocs.ui.main_window.IndexService",
        "opendocs.ui.main_window.SearchService",
        "opendocs.ui.main_window.QAService",
        "opendocs.ui.main_window.GenerationService",
        "opendocs.ui.main_window.SummaryService",
        "opendocs.ui.main_window.ArchiveService",
        "opendocs.ui.main_window.MemoryService",
        "opendocs.ui.main_window.MockProvider",
    ]
    mocks = {}
    patches = []
    for t in targets:
        p = patch(t)
        m = p.start()
        name = t.rsplit(".", 1)[-1]
        mocks[name] = m
        patches.append(p)

    # SourceService.list_sources default = no sources (wizard mode)
    mocks["SourceService"].return_value.list_sources.return_value = []
    yield mocks
    for p in patches:
        p.stop()


def test_wizard_mode_hides_nav(qtbot, tmp_path, _patch_services):
    engine = MagicMock()
    win = MainWindow(engine, hnsw_path=tmp_path / "hnsw")
    qtbot.addWidget(win)

    assert win.nav.isHidden()
    assert win.pages.currentWidget() is win.settings_page


def test_nav_visible_when_sources_exist(qtbot, tmp_path, _patch_services):
    src_mock = MagicMock()
    src_mock.source_root_id = "abc"
    src_mock.path = "/tmp/docs"
    src_mock.label = "docs"
    _patch_services["SourceService"].return_value.list_sources.return_value = [src_mock]

    engine = MagicMock()
    win = MainWindow(engine, hnsw_path=tmp_path / "hnsw")
    qtbot.addWidget(win)

    assert not win.nav.isHidden()
    assert win.pages.currentWidget() is win.search_qa_page


def test_nav_switches_pages(qtbot, tmp_path, _patch_services):
    src_mock = MagicMock()
    src_mock.source_root_id = "abc"
    _patch_services["SourceService"].return_value.list_sources.return_value = [src_mock]

    engine = MagicMock()
    win = MainWindow(engine, hnsw_path=tmp_path / "hnsw")
    qtbot.addWidget(win)

    win.nav.setCurrentRow(4)
    assert win.pages.currentWidget() is win.archive_page

    win.nav.setCurrentRow(0)
    assert win.pages.currentWidget() is win.settings_page
