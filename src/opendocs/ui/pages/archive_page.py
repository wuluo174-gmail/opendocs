"""Archive page — classify, preview, approve, execute, rollback."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from opendocs.app.archive_service import ArchiveService
from opendocs.ui.widgets.confirm_dialog import ConfirmDialog

_PLAN_COLUMNS = ["Source Path", "Target Path", "Operation", "Conflict"]


class ArchivePage(QWidget):
    """Preview → Approve → Execute → Rollback workflow for file archival."""

    def __init__(
        self,
        archive_service: ArchiveService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._archive_svc = archive_service
        self._current_plan_id: str | None = None

        self._build_ui()

    def _build_ui(self) -> None:
        self.doc_ids_input = QLineEdit()
        self.doc_ids_input.setPlaceholderText("Document IDs (comma-separated)")
        self.archive_dir_input = QLineEdit()
        self.archive_dir_input.setPlaceholderText("Base archive directory")

        self.plan_button = QPushButton("Plan")
        self.plan_button.clicked.connect(self._plan)

        input_row = QHBoxLayout()
        input_row.addWidget(self.doc_ids_input, 2)
        input_row.addWidget(self.archive_dir_input, 1)
        input_row.addWidget(self.plan_button)

        self.preview_table = QTableWidget(0, len(_PLAN_COLUMNS))
        self.preview_table.setHorizontalHeaderLabels(_PLAN_COLUMNS)
        self.preview_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch,
        )

        self.approve_button = QPushButton("Approve")
        self.approve_button.setEnabled(False)
        self.approve_button.clicked.connect(self._approve)

        self.execute_button = QPushButton("Execute")
        self.execute_button.setEnabled(False)
        self.execute_button.clicked.connect(self._execute)

        self.rollback_button = QPushButton("Rollback Last Batch")
        self.rollback_button.clicked.connect(self._rollback)

        action_row = QHBoxLayout()
        action_row.addWidget(self.approve_button)
        action_row.addWidget(self.execute_button)
        action_row.addWidget(self.rollback_button)

        self.status_label = QLabel("Ready")

        layout = QVBoxLayout(self)
        layout.addLayout(input_row)
        layout.addWidget(self.preview_table, 1)
        layout.addLayout(action_row)
        layout.addWidget(self.status_label)

    def _plan(self) -> None:
        raw_ids = self.doc_ids_input.text().strip()
        archive_dir = self.archive_dir_input.text().strip()
        if not raw_ids or not archive_dir:
            self.status_label.setText("Provide document IDs and archive directory.")
            return

        doc_ids = [d.strip() for d in raw_ids.split(",") if d.strip()]

        try:
            plan_id = self._archive_svc.classify_and_plan(
                doc_ids, base_archive_dir=archive_dir,
            )
        except Exception as exc:  # noqa: BLE001
            self.status_label.setText(f"Plan failed: {exc}")
            return

        self._current_plan_id = plan_id
        self._load_preview(plan_id)
        self.approve_button.setEnabled(True)
        self.execute_button.setEnabled(False)
        self.status_label.setText(f"Plan {plan_id[:8]} created — review and approve.")

    def _load_preview(self, plan_id: str) -> None:
        plan = self._archive_svc.get_plan(plan_id)
        moves = plan.preview_json.get("items", [])

        self.preview_table.setRowCount(len(moves))
        for i, move in enumerate(moves):
            self.preview_table.setItem(i, 0, QTableWidgetItem(move.get("source_path", "")))
            self.preview_table.setItem(i, 1, QTableWidgetItem(move.get("target_path", "")))
            self.preview_table.setItem(i, 2, QTableWidgetItem(move.get("operation_type", "move")))
            self.preview_table.setItem(
                i, 3, QTableWidgetItem("YES" if move.get("conflict") else ""),
            )

    def _approve(self) -> None:
        if self._current_plan_id is None:
            return
        self._archive_svc.approve(self._current_plan_id)
        self.approve_button.setEnabled(False)
        self.execute_button.setEnabled(True)
        self.status_label.setText("Plan approved — ready to execute.")

    def _execute(self) -> None:
        if self._current_plan_id is None:
            return

        dialog = ConfirmDialog(
            "Confirm Archive Execution",
            f"Execute plan {self._current_plan_id[:8]}?\nThis will move files on disk.",
            risk_level="high",
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        try:
            self._archive_svc.execute(self._current_plan_id)
            self.execute_button.setEnabled(False)
            self.status_label.setText("Execution complete.")
        except Exception as exc:  # noqa: BLE001
            self.status_label.setText(f"Execution failed: {exc}")

    def _rollback(self) -> None:
        dialog = ConfirmDialog(
            "Confirm Rollback",
            "Rollback the last executed batch operation?",
            risk_level="high",
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        try:
            items = self._archive_svc.rollback_last_batch()
            restored = sum(1 for it in items if it.restored)
            self.status_label.setText(f"Rolled back: {restored}/{len(items)} restored.")
        except Exception as exc:  # noqa: BLE001
            self.status_label.setText(f"Rollback failed: {exc}")
