"""Memory management page — recall, confirm, correct, disable."""

from __future__ import annotations

import uuid

from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from opendocs.memory.service import MemoryService

_TABLE_COLUMNS = ["Key", "Type", "Status", "Content"]


class MemoryPage(QWidget):
    """Manage memory items — recall, confirm, correct, disable."""

    def __init__(
        self,
        memory_service: MemoryService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._memory_svc = memory_service
        self._current_memory_id: str | None = None

        self._build_ui()

    def _build_ui(self) -> None:
        self.scope_type_combo = QComboBox()
        self.scope_type_combo.addItems(["session", "task", "user"])
        self.scope_id_input = QLineEdit()
        self.scope_id_input.setPlaceholderText("Scope ID")
        self.recall_button = QPushButton("Recall")
        self.recall_button.clicked.connect(self._recall)

        top_bar = QHBoxLayout()
        top_bar.addWidget(QLabel("Scope:"))
        top_bar.addWidget(self.scope_type_combo)
        top_bar.addWidget(self.scope_id_input, 1)
        top_bar.addWidget(self.recall_button)

        self.memory_table = QTableWidget(0, len(_TABLE_COLUMNS))
        self.memory_table.setHorizontalHeaderLabels(_TABLE_COLUMNS)
        self.memory_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch,
        )
        self.memory_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows,
        )
        self.memory_table.currentCellChanged.connect(self._on_row_selected)

        self.detail_content = QTextEdit()
        self.detail_content.setPlaceholderText("Select a memory item to view details...")

        self.confirm_button = QPushButton("Confirm")
        self.confirm_button.setEnabled(False)
        self.confirm_button.clicked.connect(self._confirm)

        self.correct_button = QPushButton("Correct")
        self.correct_button.setEnabled(False)
        self.correct_button.clicked.connect(self._correct)

        self.disable_button = QPushButton("Disable")
        self.disable_button.setEnabled(False)
        self.disable_button.clicked.connect(self._disable)

        action_row = QHBoxLayout()
        action_row.addWidget(self.confirm_button)
        action_row.addWidget(self.correct_button)
        action_row.addWidget(self.disable_button)

        self.status_label = QLabel("Ready")

        layout = QVBoxLayout(self)
        layout.addLayout(top_bar)
        layout.addWidget(self.memory_table, 1)
        layout.addWidget(QLabel("Content:"))
        layout.addWidget(self.detail_content)
        layout.addLayout(action_row)
        layout.addWidget(self.status_label)

    def _recall(self) -> None:
        scope_type = self.scope_type_combo.currentText()
        scope_id = self.scope_id_input.text().strip()
        if not scope_id:
            self.status_label.setText("Scope ID is required.")
            return

        items = self._memory_svc.recall(scope_type=scope_type, scope_id=scope_id)
        self._populate_table(items)
        self.status_label.setText(f"{len(items)} memories recalled.")

    def _populate_table(self, items: list) -> None:
        self.memory_table.setRowCount(len(items))
        for i, mem in enumerate(items):
            self.memory_table.setItem(i, 0, QTableWidgetItem(mem.key))
            self.memory_table.setItem(i, 1, QTableWidgetItem(mem.memory_type))
            self.memory_table.setItem(i, 2, QTableWidgetItem(mem.status))
            preview = mem.content[:80] + ("..." if len(mem.content) > 80 else "")
            self.memory_table.setItem(i, 3, QTableWidgetItem(preview))
            self.memory_table.item(i, 0).setData(0x0100, mem.memory_id)

    def _on_row_selected(self, row: int, _col: int, _prev_row: int, _prev_col: int) -> None:
        if row < 0:
            self._current_memory_id = None
            self.detail_content.clear()
            self._set_actions_enabled(False)
            return

        item = self.memory_table.item(row, 0)
        if item is None:
            return

        self._current_memory_id = item.data(0x0100)
        mem = self._memory_svc.get(self._current_memory_id)
        if mem is None:
            return

        self.detail_content.setPlainText(mem.content)
        self._set_actions_enabled(mem.status == "active")

    def _set_actions_enabled(self, enabled: bool) -> None:
        self.confirm_button.setEnabled(enabled)
        self.correct_button.setEnabled(enabled)
        self.disable_button.setEnabled(enabled)

    def _confirm(self) -> None:
        if self._current_memory_id is None:
            return
        self._memory_svc.confirm(self._current_memory_id, trace_id=str(uuid.uuid4()))
        self.status_label.setText("Memory confirmed.")

    def _correct(self) -> None:
        if self._current_memory_id is None:
            return
        new_content = self.detail_content.toPlainText()
        self._memory_svc.correct(
            self._current_memory_id, new_content=new_content, trace_id=str(uuid.uuid4()),
        )
        self.status_label.setText("Memory corrected.")

    def _disable(self) -> None:
        if self._current_memory_id is None:
            return
        self._memory_svc.disable(self._current_memory_id, trace_id=str(uuid.uuid4()))
        self._set_actions_enabled(False)
        self.status_label.setText("Memory disabled.")
