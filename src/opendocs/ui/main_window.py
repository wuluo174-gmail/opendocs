"""Main application window — navigation sidebar + stacked pages."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QStackedWidget,
    QWidget,
)
from sqlalchemy.engine import Engine

from opendocs.app.archive_service import ArchiveService
from opendocs.app.generation_service import GenerationService
from opendocs.app.index_service import IndexService
from opendocs.app.qa_service import QAService
from opendocs.app.search_service import SearchService
from opendocs.app.source_service import SourceService
from opendocs.app.summary_service import SummaryService
from opendocs.config.settings import OpenDocsSettings
from opendocs.memory.service import MemoryService
from opendocs.provider.mock import MockProvider
from opendocs.ui.pages.archive_page import ArchivePage
from opendocs.ui.pages.generation_page import GenerationPage
from opendocs.ui.pages.insights_page import InsightsPage
from opendocs.ui.pages.memory_page import MemoryPage
from opendocs.ui.pages.search_qa_page import SearchQAPage
from opendocs.ui.pages.settings_page import SettingsPage

_PAGE_LABELS = ["Settings", "Search / QA", "Insights", "Generation", "Archive", "Memory"]


class MainWindow(QMainWindow):
    """Top-level desktop shell with sidebar navigation."""

    def __init__(
        self,
        engine: Engine,
        *,
        hnsw_path: Path,
        settings: OpenDocsSettings | None = None,
    ) -> None:
        super().__init__()
        self.setWindowTitle("OpenDocs")
        self.resize(1100, 720)

        self._settings = settings or OpenDocsSettings()
        self._engine = engine
        self._hnsw_path = hnsw_path

        self._init_services()
        self._build_ui()
        self._check_first_run()

    # ------------------------------------------------------------------
    def _init_services(self) -> None:
        provider = MockProvider()
        rs = self._settings.retrieval
        self._source_svc = SourceService(self._engine, hnsw_path=self._hnsw_path)
        self._index_svc = IndexService(
            self._engine, hnsw_path=self._hnsw_path, watch_changes=False,
        )
        self._search_svc = SearchService(self._engine, hnsw_path=self._hnsw_path, settings=rs)
        self._qa_svc = QAService(
            self._engine,
            hnsw_path=self._hnsw_path,
            provider=provider,
            retrieval_settings=rs,
            min_evidence=self._settings.qa.min_evidence,
            min_score=self._settings.qa.min_score,
        )
        self._gen_svc = GenerationService(
            self._engine,
            hnsw_path=self._hnsw_path,
            provider=provider,
            retrieval_settings=rs,
            output_dir=self._settings.app.output_dir,
        )
        self._summary_svc = SummaryService(
            self._engine, hnsw_path=self._hnsw_path, provider=provider, retrieval_settings=rs,
        )
        self._archive_svc = ArchiveService(self._engine)
        self._memory_svc = MemoryService(self._engine, settings=self._settings.memory)

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        self.nav = QListWidget()
        self.nav.setFixedWidth(150)
        for label in _PAGE_LABELS:
            self.nav.addItem(QListWidgetItem(label))

        self.pages = QStackedWidget()
        self.settings_page = SettingsPage(self._source_svc, self._index_svc)
        self.search_qa_page = SearchQAPage(self._search_svc, self._qa_svc)
        self.insights_page = InsightsPage(self._summary_svc)
        self.generation_page = GenerationPage(self._gen_svc)
        self.archive_page = ArchivePage(self._archive_svc)
        self.memory_page = MemoryPage(self._memory_svc)

        self.pages.addWidget(self.settings_page)
        self.pages.addWidget(self.search_qa_page)
        self.pages.addWidget(self.insights_page)
        self.pages.addWidget(self.generation_page)
        self.pages.addWidget(self.archive_page)
        self.pages.addWidget(self.memory_page)

        self.nav.currentRowChanged.connect(self.pages.setCurrentIndex)

        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.nav)
        layout.addWidget(self.pages, 1)
        self.setCentralWidget(container)

    # ------------------------------------------------------------------
    def _check_first_run(self) -> None:
        sources = self._source_svc.list_sources()
        if not sources:
            self._enter_wizard_mode()
        else:
            self.nav.setCurrentRow(1)

    def _enter_wizard_mode(self) -> None:
        self.nav.hide()
        self.pages.setCurrentWidget(self.settings_page)
        self.settings_page.setup_complete.connect(self._exit_wizard_mode)

    def _exit_wizard_mode(self) -> None:
        self.nav.show()
        self.nav.setCurrentRow(1)
