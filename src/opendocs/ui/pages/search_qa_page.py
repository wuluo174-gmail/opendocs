"""Unified search + QA page with evidence panel and answer display."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from opendocs.app.qa_service import QAService
from opendocs.app.search_service import SearchService
from opendocs.qa.models import AnswerStatus
from opendocs.retrieval.evidence import SearchResult
from opendocs.retrieval.evidence_locator import EvidenceLocation
from opendocs.ui.document_preview_panel import DocumentPreviewPanel
from opendocs.ui.evidence_panel import EvidencePanel

_STATUS_DISPLAY: dict[AnswerStatus, tuple[str, str]] = {
    AnswerStatus.FACTUAL: ("factual", "#4caf50"),
    AnswerStatus.INSUFFICIENT_EVIDENCE: ("insufficient_evidence", "#ff9800"),
    AnswerStatus.CONFLICT: ("conflict", "#f44336"),
}


class SearchQAPage(QWidget):
    """Search documents and ask questions with citation support."""

    evidence_activated = Signal(object)

    def __init__(
        self,
        search_service: SearchService,
        qa_service: QAService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._search_svc = search_service
        self._qa_svc = qa_service
        self._current_result: SearchResult | None = None

        self._build_ui()
        self._connect_signals()

    def _build_ui(self) -> None:
        self.query_input = QLineEdit()
        self.query_input.setPlaceholderText("Search or ask a question...")
        self.search_button = QPushButton("Search")
        self.ask_button = QPushButton("Ask AI")

        top_bar = QHBoxLayout()
        top_bar.addWidget(self.query_input, 1)
        top_bar.addWidget(self.search_button)
        top_bar.addWidget(self.ask_button)

        self.results_list = QListWidget()
        self.evidence_panel = EvidencePanel()
        self.document_preview_panel = DocumentPreviewPanel()

        self.qa_status_label = QLabel()
        self.qa_answer_text = QTextEdit()
        self.qa_answer_text.setReadOnly(True)
        self.qa_citations_list = QListWidget()
        self.qa_conflict_label = QLabel()
        self.qa_conflict_label.setWordWrap(True)
        self.qa_conflict_label.hide()

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(self.evidence_panel)
        right_layout.addWidget(self.document_preview_panel)
        right_layout.addWidget(self.qa_status_label)
        right_layout.addWidget(self.qa_answer_text)
        right_layout.addWidget(self.qa_citations_list)
        right_layout.addWidget(self.qa_conflict_label)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.results_list)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        layout = QVBoxLayout(self)
        layout.addLayout(top_bar)
        layout.addWidget(splitter, 1)

    def _connect_signals(self) -> None:
        self.search_button.clicked.connect(self._run_search)
        self.query_input.returnPressed.connect(self._run_search)
        self.ask_button.clicked.connect(self._run_qa)
        self.results_list.currentItemChanged.connect(self._on_result_selected)
        self.evidence_panel.locate_requested.connect(self._locate_evidence)
        self.evidence_panel.open_requested.connect(self._open_evidence)

    def _run_search(self) -> None:
        query = self.query_input.text().strip()
        self.results_list.clear()
        self._current_result = None
        self.evidence_panel.set_location(None)
        self.document_preview_panel.set_preview(None)

        if not query:
            return

        response = self._search_svc.search(query)
        for result in response.results:
            item = QListWidgetItem(f"{result.title} | {result.path}", self.results_list)
            item.setData(Qt.ItemDataRole.UserRole, result)

        if response.results:
            self.results_list.setCurrentRow(0)

    def _run_qa(self) -> None:
        query = self.query_input.text().strip()
        if not query:
            return

        response = self._qa_svc.ask(query)
        label_text, color = _STATUS_DISPLAY[response.status]
        self.qa_status_label.setText(label_text)
        self.qa_status_label.setStyleSheet(
            f"background-color: {color}; color: white; padding: 4px; font-weight: bold;"
        )
        self.qa_answer_text.setPlainText(response.answer_text)

        self.qa_citations_list.clear()
        for cit in response.citations:
            self.qa_citations_list.addItem(f"[{cit.path}] {cit.quote_preview}")

        if response.status == AnswerStatus.CONFLICT and response.conflict_sources:
            lines = []
            for group in response.conflict_sources:
                paths = ", ".join(c.path for c in group)
                lines.append(paths)
            self.qa_conflict_label.setText("Conflict sources:\n" + "\n".join(lines))
            self.qa_conflict_label.show()
        else:
            self.qa_conflict_label.hide()

    def _on_result_selected(
        self, current: QListWidgetItem | None, _prev: QListWidgetItem | None,
    ) -> None:
        if current is None:
            self._current_result = None
            self.evidence_panel.set_location(None)
            self.document_preview_panel.set_preview(None)
            return

        result = current.data(Qt.ItemDataRole.UserRole)
        if not isinstance(result, SearchResult):
            return

        self._current_result = result
        location = self._search_svc.locate_evidence(result.doc_id, result.chunk_id)
        self.evidence_panel.set_location(location)
        self.document_preview_panel.set_preview(None)

    def _locate_evidence(self, location: object) -> None:
        if not isinstance(location, EvidenceLocation) or self._current_result is None:
            return
        self.evidence_activated.emit(location)
        preview = self._search_svc.load_evidence_preview(
            self._current_result.doc_id, self._current_result.chunk_id,
        )
        self.document_preview_panel.set_preview(preview)

    def _open_evidence(self, location: object) -> None:
        if not isinstance(location, EvidenceLocation) or self._current_result is None:
            return
        if location.can_open:
            self._search_svc.open_evidence(
                self._current_result.doc_id, self._current_result.chunk_id,
            )
