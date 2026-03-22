"""In-app citation preview panel for deterministic local evidence review."""

from __future__ import annotations

from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QLabel, QTextEdit, QVBoxLayout, QWidget

from opendocs.retrieval.evidence_locator import EvidencePreview


def _format_preview_locator(preview: EvidencePreview) -> str:
    parts = []
    if preview.page_no is not None:
        parts.append(f"page={preview.page_no}")
    if preview.paragraph_range is not None:
        parts.append(f"paragraph={preview.paragraph_range}")
    parts.append(f"chars={preview.char_range}")
    return " | ".join(parts)


class DocumentPreviewPanel(QWidget):
    """Display an in-app excerpt anchored to the selected citation."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._current_preview: EvidencePreview | None = None

        self.path_label = QLabel("Preview Path: -", self)
        self.locator_label = QLabel("Preview Locator: -", self)
        self.preview_text = QTextEdit(self)
        self.preview_text.setReadOnly(True)

        layout = QVBoxLayout(self)
        layout.addWidget(self.path_label)
        layout.addWidget(self.locator_label)
        layout.addWidget(self.preview_text)

    @property
    def current_preview(self) -> EvidencePreview | None:
        return self._current_preview

    def set_preview(self, preview: EvidencePreview | None) -> None:
        self._current_preview = preview
        self.preview_text.setExtraSelections([])

        if preview is None:
            self.path_label.setText("Preview Path: -")
            self.locator_label.setText("Preview Locator: -")
            self.preview_text.setPlainText("")
            return

        self.path_label.setText(f"Preview Path: {preview.path}")
        self.locator_label.setText(f"Preview Locator: {_format_preview_locator(preview)}")
        self.preview_text.setPlainText(preview.preview_text)
        self._highlight_range(preview.highlight_start, preview.highlight_end)

    def _highlight_range(self, start: int, end: int) -> None:
        if start >= end:
            return

        cursor = self.preview_text.textCursor()
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)

        selection = QTextEdit.ExtraSelection()
        selection.cursor = cursor
        fmt = QTextCharFormat()
        fmt.setBackground(QColor("#fff59d"))
        selection.format = fmt

        self.preview_text.setExtraSelections([selection])
        self.preview_text.setTextCursor(cursor)
        self.preview_text.ensureCursorVisible()
