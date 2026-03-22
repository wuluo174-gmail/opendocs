"""Settings page — root directory management, mode, provider, first-time indexing."""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from opendocs.app.index_service import IndexService
from opendocs.app.source_service import SourceService


class _IndexWorker(QThread):
    finished = Signal(str)
    failed = Signal(str)

    def __init__(self, index_service: IndexService, source_root_id: str) -> None:
        super().__init__()
        self._index_svc = index_service
        self._source_root_id = source_root_id

    def run(self) -> None:
        try:
            result = self._index_svc.full_index_source(self._source_root_id)
            self.finished.emit(
                f"Indexed {result.success_count}/{result.total} "
                f"(failed: {result.failed_count})"
            )
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class SettingsPage(QWidget):
    """Configure source roots and trigger first-time indexing."""

    setup_complete = Signal()

    def __init__(
        self,
        source_service: SourceService,
        index_service: IndexService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._source_svc = source_service
        self._index_svc = index_service
        self._worker: _IndexWorker | None = None

        self._build_ui()
        self._refresh_source_list()

    def _build_ui(self) -> None:
        self.path_input = QLineEdit()
        self.path_input.setPlaceholderText("Document root directory")
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse)

        path_row = QHBoxLayout()
        path_row.addWidget(self.path_input, 1)
        path_row.addWidget(browse_btn)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["local", "hybrid"])
        self.provider_combo = QComboBox()
        self.provider_combo.addItems(["mock", "ollama"])

        config_row = QHBoxLayout()
        config_row.addWidget(QLabel("Mode:"))
        config_row.addWidget(self.mode_combo)
        config_row.addWidget(QLabel("Provider:"))
        config_row.addWidget(self.provider_combo)

        self.add_button = QPushButton("Add & Index")
        self.add_button.clicked.connect(self._add_and_index)

        self.source_list = QListWidget()
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        self.status_label = QLabel("Ready")

        layout = QVBoxLayout(self)
        layout.addLayout(path_row)
        layout.addLayout(config_row)
        layout.addWidget(self.add_button)
        layout.addWidget(self.source_list)
        layout.addWidget(self.progress)
        layout.addWidget(self.status_label)

    def _browse(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select Document Root")
        if path:
            self.path_input.setText(path)

    def _add_and_index(self) -> None:
        path = self.path_input.text().strip()
        if not path:
            self.status_label.setText("Path is empty.")
            return

        self.add_button.setEnabled(False)
        self.status_label.setText("Adding source...")

        try:
            source = self._source_svc.add_source(path)
        except Exception as exc:  # noqa: BLE001
            self.status_label.setText(f"Error: {exc}")
            self.add_button.setEnabled(True)
            return

        self._refresh_source_list()
        self.status_label.setText("Indexing...")
        self.progress.show()

        self._worker = _IndexWorker(self._index_svc, source.source_root_id)
        self._worker.finished.connect(self._on_index_done)
        self._worker.failed.connect(self._on_index_failed)
        self._worker.start()

    def _on_index_done(self, summary: str) -> None:
        self.progress.hide()
        self.add_button.setEnabled(True)
        self.status_label.setText(summary)
        self.path_input.clear()
        self.setup_complete.emit()

    def _on_index_failed(self, error: str) -> None:
        self.progress.hide()
        self.add_button.setEnabled(True)
        self.status_label.setText(f"Index failed: {error}")

    def _refresh_source_list(self) -> None:
        self.source_list.clear()
        for src in self._source_svc.list_sources():
            self.source_list.addItem(f"{src.label or src.path}  [{src.source_root_id[:8]}]")
