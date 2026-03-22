"""Preview-and-confirm dialog for high-risk operations."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class ConfirmDialog(QDialog):
    """Show a preview and require explicit confirmation before proceeding."""

    def __init__(
        self,
        title: str,
        preview_text: str,
        *,
        risk_level: str = "low",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(480)

        title_label = QLabel(title, self)
        if risk_level == "high":
            title_label.setStyleSheet("color: #d32f2f; font-weight: bold;")

        preview = QTextEdit(self)
        preview.setReadOnly(True)
        preview.setPlainText(preview_text)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(title_label)
        layout.addWidget(preview)
        layout.addWidget(buttons)
