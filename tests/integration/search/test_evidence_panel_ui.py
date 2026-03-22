"""PySide6 evidence-panel tests for S4 citation display and click-through."""

from __future__ import annotations

import os
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from sqlalchemy import text

from opendocs.retrieval.evidence_locator import EvidenceLocation
from opendocs.storage.db import session_scope
from opendocs.ui import EvidencePanel, SearchWindow


class TestEvidencePanelUi:
    def test_panel_displays_pdf_locator_and_emits_locate_request(self, qtbot) -> None:
        panel = EvidencePanel()
        qtbot.addWidget(panel)

        location = EvidenceLocation(
            path="papers/research_paper.pdf",
            page_no=3,
            paragraph_range=None,
            char_range="120-240",
            quote_preview="PDF evidence preview",
            can_open=True,
        )
        panel.set_location(location)

        assert panel.path_label.text() == "Path: papers/research_paper.pdf"
        assert "page=3" in panel.locator_label.text()
        assert panel.preview_text.toPlainText() == "PDF evidence preview"

        with qtbot.waitSignal(panel.locate_requested, timeout=1000) as blocker:
            qtbot.mouseClick(panel.locate_button, Qt.MouseButton.LeftButton)

        emitted = blocker.args[0]
        assert emitted.page_no == 3
        assert emitted.char_range == "120-240"

    def test_search_window_locates_preview_then_opens_and_reveals(
        self, qtbot, search_service
    ) -> None:
        window = SearchWindow(search_service)
        qtbot.addWidget(window)
        window.show()

        window.query_input.setText("项目进度")
        qtbot.mouseClick(window.search_button, Qt.MouseButton.LeftButton)
        qtbot.waitUntil(lambda: window.results_list.count() > 0)
        qtbot.waitUntil(lambda: window.evidence_panel.current_location is not None)

        location = window.evidence_panel.current_location
        assert location is not None
        assert location.quote_preview
        assert "Path:" in window.evidence_panel.path_label.text()
        assert "paragraph=" in window.evidence_panel.locator_label.text()
        assert not location.path.startswith("/")

        with qtbot.waitSignal(window.evidence_activated, timeout=1000):
            qtbot.mouseClick(window.evidence_panel.locate_button, Qt.MouseButton.LeftButton)

        qtbot.waitUntil(lambda: window.document_preview_panel.current_preview is not None)
        preview = window.document_preview_panel.current_preview
        assert preview is not None
        assert preview.preview_text
        assert preview.highlight_end > preview.highlight_start
        assert not preview.path.startswith("/")

        with patch.object(search_service, "open_evidence", return_value=True) as open_mock:
            qtbot.mouseClick(window.evidence_panel.open_button, Qt.MouseButton.LeftButton)

        result = window.results_list.currentItem().data(Qt.ItemDataRole.UserRole)
        open_mock.assert_called_once_with(result.doc_id, result.chunk_id)

        with patch.object(search_service, "reveal_evidence", return_value=True) as reveal_mock:
            qtbot.mouseClick(window.evidence_panel.reveal_button, Qt.MouseButton.LeftButton)

        reveal_mock.assert_called_once_with(result.doc_id, result.chunk_id)

    def test_search_window_supports_source_and_time_filters(
        self, qtbot, indexed_search_env
    ) -> None:
        engine, _, hnsw_path = indexed_search_env
        with session_scope(engine) as session:
            source_root_id = session.execute(
                text("SELECT source_root_id FROM documents WHERE path LIKE :pattern"),
                {"pattern": "%zh_project_plan.md"},
            ).scalar_one()

        from opendocs.app.search_service import SearchService

        window = SearchWindow(SearchService(engine, hnsw_path=hnsw_path))
        qtbot.addWidget(window)
        window.show()

        window.query_input.setText("项目")
        window.source_root_filter_input.setText(source_root_id)
        window.time_from_filter_input.setText("2026-03-01T00:00:00")
        window.time_to_filter_input.setText("2026-03-20T23:59:59")

        qtbot.mouseClick(window.search_button, Qt.MouseButton.LeftButton)
        qtbot.waitUntil(lambda: window.results_list.count() > 0)

        results = [
            window.results_list.item(idx).text() for idx in range(window.results_list.count())
        ]
        assert any("zh_project_plan.md" in result for result in results)

    def test_search_window_rejects_partial_time_range(self, qtbot, search_service) -> None:
        window = SearchWindow(search_service)
        qtbot.addWidget(window)
        window.show()

        window.query_input.setText("项目")
        window.time_from_filter_input.setText("2026-03-01T00:00:00")

        qtbot.mouseClick(window.search_button, Qt.MouseButton.LeftButton)

        assert window.status_label.text() == "Time range requires both start and end."
