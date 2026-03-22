"""Multi-document summary and insights page."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from opendocs.app.summary_service import SummaryService
from opendocs.generation.models import SummaryResponse


class InsightsPage(QWidget):
    """Summarize multiple documents, display insights, export Markdown."""

    def __init__(
        self,
        summary_service: SummaryService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._summary_svc = summary_service
        self._last_response: SummaryResponse | None = None

        self._build_ui()

    def _build_ui(self) -> None:
        self.query_input = QLineEdit()
        self.query_input.setPlaceholderText("Topic or question to summarize...")
        self.summarize_button = QPushButton("Summarize")
        self.summarize_button.clicked.connect(self._run_summarize)

        top_bar = QHBoxLayout()
        top_bar.addWidget(self.query_input, 1)
        top_bar.addWidget(self.summarize_button)

        self.insights_list = QListWidget()
        self.summary_text = QTextEdit()
        self.summary_text.setReadOnly(True)

        self.export_button = QPushButton("Export Markdown")
        self.export_button.setEnabled(False)
        self.export_button.clicked.connect(self._export)

        self.status_label = QLabel("Ready")

        layout = QVBoxLayout(self)
        layout.addLayout(top_bar)
        layout.addWidget(QLabel("Insights:"))
        layout.addWidget(self.insights_list)
        layout.addWidget(QLabel("Summary:"))
        layout.addWidget(self.summary_text, 1)
        layout.addWidget(self.export_button)
        layout.addWidget(self.status_label)

    def _run_summarize(self) -> None:
        query = self.query_input.text().strip()
        if not query:
            return

        self.status_label.setText("Summarizing...")
        response = self._summary_svc.summarize(query)
        self._last_response = response

        self.summary_text.setPlainText(response.summary_text)

        self.insights_list.clear()
        for item in response.insights:
            self.insights_list.addItem(f"[{item.insight_type}] {item.text}")

        self.export_button.setEnabled(True)
        self.status_label.setText(
            f"Done — {len(response.insights)} insights, "
            f"{len(response.citations)} citations"
        )

    def _export(self) -> None:
        if self._last_response is None:
            return

        md = self._summary_svc.export(self._last_response)
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Markdown", "summary.md", "Markdown (*.md)",
        )
        if not path:
            return

        with open(path, "w", encoding="utf-8") as f:
            f.write(md)
        self.status_label.setText(f"Exported to {path}")
