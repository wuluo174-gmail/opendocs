"""PySide6 evidence-panel tests for S4 citation display and click-through."""

from __future__ import annotations

import os
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt

from opendocs.exceptions import SearchExecutionError
from opendocs.retrieval.evidence_locator import EvidenceLocation, ExternalActionResult
from opendocs.ui import EvidencePanel, SearchWindow


class TestEvidencePanelUi:
    @staticmethod
    def _launched_action(action: str = "open") -> ExternalActionResult:
        return ExternalActionResult(
            action=action,
            status="launched",
            target_path="/tmp/example.txt",
            external_target="file:///tmp/example.txt",
            locator_hint_applied=True,
            message="external request launched",
        )

    @staticmethod
    def _failed_action(action: str = "open") -> ExternalActionResult:
        return ExternalActionResult(
            action=action,
            status="launch_failed",
            target_path="/tmp/example.txt",
            external_target="file:///tmp/example.txt",
            locator_hint_applied=True,
            message=f"failed to launch external {action} request",
            error="boom",
        )

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
            external_jump_supported=True,
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

    def test_search_window_locates_preview_without_auto_open_for_non_pdf_citations(
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
        assert location.external_jump_supported is False

        result = window.results_list.currentItem().data(Qt.ItemDataRole.UserRole)

        with patch.object(
            search_service,
            "open_evidence",
            return_value=self._launched_action("open"),
        ) as locate_open_mock:
            with qtbot.waitSignal(window.evidence_activated, timeout=1000):
                qtbot.mouseClick(window.evidence_panel.locate_button, Qt.MouseButton.LeftButton)

        qtbot.waitUntil(lambda: window.document_preview_panel.current_preview is not None)
        preview = window.document_preview_panel.current_preview
        assert preview is not None
        assert preview.preview_text
        assert preview.highlight_end > preview.highlight_start
        assert not preview.path.startswith("/")
        assert "Evidence preview ready." in window.status_label.text()
        assert "external request launched" not in window.status_label.text()
        locate_open_mock.assert_not_called()

        with patch.object(
            search_service,
            "open_evidence",
            return_value=self._launched_action("open"),
        ) as open_mock:
            qtbot.mouseClick(window.evidence_panel.open_button, Qt.MouseButton.LeftButton)

        open_mock.assert_called_once_with(result.doc_id, result.chunk_id)

        with patch.object(
            search_service,
            "reveal_evidence",
            return_value=self._launched_action("reveal"),
        ) as reveal_mock:
            qtbot.mouseClick(window.evidence_panel.reveal_button, Qt.MouseButton.LeftButton)

        reveal_mock.assert_called_once_with(result.doc_id, result.chunk_id)

    def test_search_window_keeps_preview_when_external_open_fails(
        self, qtbot, search_service
    ) -> None:
        window = SearchWindow(search_service)
        qtbot.addWidget(window)
        window.show()

        window.query_input.setText("项目进度")
        qtbot.mouseClick(window.search_button, Qt.MouseButton.LeftButton)
        qtbot.waitUntil(lambda: window.results_list.count() > 0)
        qtbot.waitUntil(lambda: window.evidence_panel.current_location is not None)

        with qtbot.waitSignal(window.evidence_activated, timeout=1000):
            qtbot.mouseClick(window.evidence_panel.locate_button, Qt.MouseButton.LeftButton)

        qtbot.waitUntil(lambda: window.document_preview_panel.current_preview is not None)
        assert window.document_preview_panel.current_preview is not None
        with patch.object(
            search_service,
            "open_evidence",
            return_value=self._failed_action("open"),
        ):
            qtbot.mouseClick(window.evidence_panel.open_button, Qt.MouseButton.LeftButton)

        assert window.document_preview_panel.current_preview is not None
        assert "failed to launch external open request" in window.status_label.text()

    def test_search_window_supports_path_and_time_filters(
        self,
        qtbot,
        indexed_search_env,
        search_runtime,
    ) -> None:
        _engine, _, _hnsw_path = indexed_search_env
        window = SearchWindow(search_runtime.build_search_service())
        qtbot.addWidget(window)
        window.show()

        window.query_input.setText("项目")
        window.root_filter_input.setText("corpus")
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

    def test_search_window_handles_backend_failure(self, qtbot, search_service) -> None:
        window = SearchWindow(search_service)
        qtbot.addWidget(window)
        window.show()

        window.query_input.setText("项目进度")

        with patch.object(
            search_service,
            "search",
            side_effect=SearchExecutionError("search backend failed"),
        ):
            qtbot.mouseClick(window.search_button, Qt.MouseButton.LeftButton)

        assert window.status_label.text() == "search backend failed"
