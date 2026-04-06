"""Minimal evidence panel for S4 citation review and click-through."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from opendocs.retrieval.evidence_locator import EvidenceLocation


def _format_locator(location: EvidenceLocation) -> str:
    parts = [f"path={location.path}"]
    if location.page_no is not None:
        parts.append(f"page={location.page_no}")
    if location.paragraph_range is not None:
        parts.append(f"paragraph={location.paragraph_range}")
    parts.append(f"chars={location.char_range}")
    return " | ".join(parts)


class EvidencePanel(QWidget):
    """Display citation metadata and emit click-through requests."""

    locate_requested = Signal(object)
    open_requested = Signal(object)
    reveal_requested = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._current_location: EvidenceLocation | None = None

        self.path_label = QLabel("Path: -", self)
        self.locator_label = QLabel("Locator: -", self)
        self.preview_text = QTextEdit(self)
        self.preview_text.setReadOnly(True)
        self.locate_button = QPushButton("Go To Citation", self)
        self.locate_button.setEnabled(False)
        self.locate_button.clicked.connect(self._emit_locate_requested)
        self.open_button = QPushButton("Open File", self)
        self.open_button.clicked.connect(self._emit_open_requested)
        self.open_button.setEnabled(False)
        self.reveal_button = QPushButton("Reveal Folder", self)
        self.reveal_button.clicked.connect(self._emit_reveal_requested)
        self.reveal_button.setEnabled(False)

        layout = QVBoxLayout(self)
        layout.addWidget(self.path_label)
        layout.addWidget(self.locator_label)
        layout.addWidget(self.preview_text)
        button_row = QHBoxLayout()
        button_row.addWidget(self.locate_button)
        button_row.addWidget(self.open_button)
        button_row.addWidget(self.reveal_button)
        layout.addLayout(button_row)

    @property
    def current_location(self) -> EvidenceLocation | None:
        return self._current_location

    def set_location(self, location: EvidenceLocation | None) -> None:
        self._current_location = location
        if location is None:
            self.path_label.setText("Path: -")
            self.locator_label.setText("Locator: -")
            self.preview_text.setPlainText("")
            self.locate_button.setEnabled(False)
            self.open_button.setEnabled(False)
            self.reveal_button.setEnabled(False)
            return

        self.path_label.setText(f"Path: {location.path}")
        self.locator_label.setText(f"Locator: {_format_locator(location)}")
        self.preview_text.setPlainText(location.quote_preview)
        self.locate_button.setEnabled(True)
        self.open_button.setEnabled(location.can_open)
        self.reveal_button.setEnabled(location.can_open)

    def _emit_locate_requested(self) -> None:
        if self._current_location is None:
            return
        self.locate_requested.emit(self._current_location)

    def _emit_open_requested(self) -> None:
        if self._current_location is None:
            return
        self.open_requested.emit(self._current_location)

    def _emit_reveal_requested(self) -> None:
        if self._current_location is None:
            return
        self.reveal_requested.emit(self._current_location)
