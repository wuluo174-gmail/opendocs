"""Minimal PySide6 search shell for S4 evidence inspection."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from opendocs.app.search_service import SearchService
from opendocs.exceptions import SearchExecutionError
from opendocs.retrieval.evidence import SearchResult
from opendocs.retrieval.evidence_locator import EvidenceLocation, ExternalActionResult
from opendocs.retrieval.filters import SearchFilter
from opendocs.ui.document_preview_panel import DocumentPreviewPanel
from opendocs.ui.evidence_panel import EvidencePanel


class SearchWindow(QWidget):
    """Minimal search/result/citation shell used by S4 tests and manual review."""

    evidence_activated = Signal(object)

    def __init__(
        self,
        search_service: SearchService,
        parent: QWidget | None = None,
        *,
        auto_open_on_locate: bool = True,
    ) -> None:
        super().__init__(parent)
        self._search_service = search_service
        self._auto_open_on_locate = auto_open_on_locate
        self._current_result: SearchResult | None = None

        self.query_input = QLineEdit(self)
        self.query_input.setPlaceholderText("Search query")
        self.root_filter_input = QLineEdit(self)
        self.root_filter_input.setPlaceholderText("Root")
        self.directory_filter_input = QLineEdit(self)
        self.directory_filter_input.setPlaceholderText("Dir")
        self.category_filter_input = QLineEdit(self)
        self.category_filter_input.setPlaceholderText("Category")
        self.tags_filter_input = QLineEdit(self)
        self.tags_filter_input.setPlaceholderText("Tags")
        self.file_type_filter_input = QLineEdit(self)
        self.file_type_filter_input.setPlaceholderText("Type")
        self.sensitivity_filter_input = QLineEdit(self)
        self.sensitivity_filter_input.setPlaceholderText("Sensitivity")
        self.time_from_filter_input = QLineEdit(self)
        self.time_from_filter_input.setPlaceholderText("Time from")
        self.time_to_filter_input = QLineEdit(self)
        self.time_to_filter_input.setPlaceholderText("Time to")
        self.search_button = QPushButton("Search", self)
        self.results_list = QListWidget(self)
        self.status_label = QLabel("Ready", self)
        self.evidence_panel = EvidencePanel(self)
        self.document_preview_panel = DocumentPreviewPanel(self)

        controls = QHBoxLayout()
        controls.addWidget(self.query_input)
        controls.addWidget(self.search_button)

        filter_bar_top = QHBoxLayout()
        filter_bar_top.addWidget(self.root_filter_input)
        filter_bar_top.addWidget(self.directory_filter_input)
        filter_bar_top.addWidget(self.category_filter_input)
        filter_bar_top.addWidget(self.tags_filter_input)

        filter_bar_bottom = QHBoxLayout()
        filter_bar_bottom.addWidget(self.file_type_filter_input)
        filter_bar_bottom.addWidget(self.sensitivity_filter_input)
        filter_bar_bottom.addWidget(self.time_from_filter_input)
        filter_bar_bottom.addWidget(self.time_to_filter_input)

        layout = QVBoxLayout(self)
        layout.addLayout(controls)
        layout.addLayout(filter_bar_top)
        layout.addLayout(filter_bar_bottom)
        layout.addWidget(self.results_list)
        layout.addWidget(self.status_label)
        layout.addWidget(self.evidence_panel)
        layout.addWidget(self.document_preview_panel)

        self.search_button.clicked.connect(self.run_search)
        self.query_input.returnPressed.connect(self.run_search)
        self.results_list.currentItemChanged.connect(self._on_result_selected)
        self.evidence_panel.locate_requested.connect(self._locate_selected_evidence)
        self.evidence_panel.open_requested.connect(self._open_selected_evidence)
        self.evidence_panel.reveal_requested.connect(self._reveal_selected_evidence)

    def run_search(self) -> None:
        query = self.query_input.text().strip()
        self.results_list.clear()
        self._current_result = None
        self.evidence_panel.set_location(None)
        self.document_preview_panel.set_preview(None)

        if not query:
            self.status_label.setText("Query is empty.")
            return

        try:
            filters = self._collect_filters()
        except ValueError as exc:
            self.status_label.setText(str(exc))
            return

        try:
            response = self._search_service.search(query, filters=filters)
        except ValueError as exc:
            self.status_label.setText(str(exc))
            return
        except SearchExecutionError as exc:
            self.status_label.setText(str(exc))
            return
        self.status_label.setText(f"{len(response.results)} results")

        for result in response.results:
            item = QListWidgetItem(f"{result.title} | {result.path}", self.results_list)
            item.setData(Qt.ItemDataRole.UserRole, result)

        if response.results:
            self.results_list.setCurrentRow(0)

    def _collect_filters(self) -> SearchFilter | None:
        source_roots = self._csv_values(self.root_filter_input.text())
        directory_prefixes = self._csv_values(self.directory_filter_input.text())
        categories = self._csv_values(self.category_filter_input.text())
        tags = self._csv_values(self.tags_filter_input.text())
        file_types = self._csv_values(self.file_type_filter_input.text())
        sensitivity_levels = self._csv_values(self.sensitivity_filter_input.text())
        time_range = self._time_range_values()

        if not any(
            [
                source_roots,
                directory_prefixes,
                categories,
                tags,
                file_types,
                time_range,
                sensitivity_levels,
            ]
        ):
            return None

        return SearchFilter(
            source_roots=source_roots,
            directory_prefixes=directory_prefixes,
            categories=categories,
            tags=tags,
            file_types=file_types,
            time_range=time_range,
            sensitivity_levels=sensitivity_levels,
        )

    @staticmethod
    def _csv_values(value: str) -> list[str] | None:
        items = [item.strip() for item in value.split(",") if item.strip()]
        return items or None

    def _time_range_values(self) -> tuple[datetime, datetime] | None:
        start_text = self.time_from_filter_input.text().strip()
        end_text = self.time_to_filter_input.text().strip()
        if not start_text and not end_text:
            return None
        if not start_text or not end_text:
            raise ValueError("Time range requires both start and end.")
        return (
            self._parse_time_input(start_text),
            self._parse_time_input(end_text),
        )

    @staticmethod
    def _parse_time_input(value: str) -> datetime:
        try:
            return datetime.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"Invalid time value: {value}") from exc

    def _on_result_selected(
        self,
        current: QListWidgetItem | None,
        _: QListWidgetItem | None,
    ) -> None:
        if current is None:
            self._current_result = None
            self.evidence_panel.set_location(None)
            self.document_preview_panel.set_preview(None)
            return

        result = current.data(Qt.ItemDataRole.UserRole)
        if not isinstance(result, SearchResult):
            self._current_result = None
            self.evidence_panel.set_location(None)
            self.document_preview_panel.set_preview(None)
            return

        self._current_result = result
        location = self._search_service.locate_evidence(result.doc_id, result.chunk_id)
        self.evidence_panel.set_location(location)
        self.document_preview_panel.set_preview(None)

    def _locate_selected_evidence(self, location: object) -> None:
        if not isinstance(location, EvidenceLocation):
            return
        if self._current_result is None:
            return
        self.evidence_activated.emit(location)
        activation = self._search_service.activate_evidence(
            self._current_result.doc_id,
            self._current_result.chunk_id,
            auto_open=self._auto_open_on_locate and location.can_open,
        )
        self.document_preview_panel.set_preview(activation.preview)
        self.status_label.setText(
            self._build_locate_status(
                preview_ready=activation.preview is not None,
                action=activation.external_action,
            )
        )

    def _open_selected_evidence(self, location: object) -> None:
        if not isinstance(location, EvidenceLocation):
            return
        if self._current_result is None or not location.can_open:
            return
        action = self._search_service.open_evidence(
            self._current_result.doc_id,
            self._current_result.chunk_id,
        )
        self.status_label.setText(action.message)

    def _reveal_selected_evidence(self, location: object) -> None:
        if not isinstance(location, EvidenceLocation):
            return
        if self._current_result is None or not location.can_open:
            return
        action = self._search_service.reveal_evidence(
            self._current_result.doc_id,
            self._current_result.chunk_id,
        )
        self.status_label.setText(action.message)

    @staticmethod
    def _build_locate_status(
        *,
        preview_ready: bool,
        action: ExternalActionResult | None,
    ) -> str:
        preview_status = (
            "Evidence preview ready." if preview_ready else "Evidence preview unavailable."
        )
        if action is None:
            return preview_status
        return f"{preview_status} {action.message.rstrip('.')}."
