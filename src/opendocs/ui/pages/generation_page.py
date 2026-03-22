"""Document generation page — template selection, draft editing, save with confirmation."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from opendocs.app.generation_service import GenerationService
from opendocs.generation.models import Draft
from opendocs.ui.widgets.confirm_dialog import ConfirmDialog


class GenerationPage(QWidget):
    """Generate document drafts from templates, edit, and save with confirmation."""

    def __init__(
        self,
        generation_service: GenerationService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._gen_svc = generation_service
        self._current_draft: Draft | None = None

        self._build_ui()
        self._load_templates()

    def _build_ui(self) -> None:
        self.query_input = QLineEdit()
        self.query_input.setPlaceholderText("Generation query...")
        self.template_combo = QComboBox()
        self.generate_button = QPushButton("Generate")
        self.generate_button.clicked.connect(self._generate)

        top_bar = QHBoxLayout()
        top_bar.addWidget(self.query_input, 1)
        top_bar.addWidget(self.template_combo)
        top_bar.addWidget(self.generate_button)

        self.draft_editor = QTextEdit()
        self.draft_editor.setPlaceholderText("Generated draft will appear here...")

        self.citations_list = QListWidget()
        self.save_button = QPushButton("Save Draft")
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self._save)

        self.status_label = QLabel("Ready")

        layout = QVBoxLayout(self)
        layout.addLayout(top_bar)
        layout.addWidget(self.draft_editor, 1)
        layout.addWidget(QLabel("Citations:"))
        layout.addWidget(self.citations_list)
        layout.addWidget(self.save_button)
        layout.addWidget(self.status_label)

    def _load_templates(self) -> None:
        self.template_combo.clear()
        self.template_combo.addItem("(auto)")
        for name in self._gen_svc.list_templates():
            self.template_combo.addItem(name)

    def _generate(self) -> None:
        query = self.query_input.text().strip()
        if not query:
            return

        template = self.template_combo.currentText()
        template_name = None if template == "(auto)" else template

        self.status_label.setText("Generating...")
        draft = self._gen_svc.generate(query, template_name=template_name)
        self._current_draft = draft

        self.draft_editor.setPlainText(draft.content)
        self.citations_list.clear()
        for cit in draft.citations:
            self.citations_list.addItem(f"[{cit.path}] {cit.quote_preview}")

        self.save_button.setEnabled(True)
        self.status_label.setText("Draft generated — edit and save when ready.")

    def _save(self) -> None:
        if self._current_draft is None:
            return

        edited_content = self.draft_editor.toPlainText()
        if edited_content != self._current_draft.content:
            self._current_draft = self._gen_svc.edit_draft(self._current_draft, edited_content)

        preview = edited_content[:500] + ("..." if len(edited_content) > 500 else "")
        dialog = ConfirmDialog("Confirm Save", preview, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        path = self._gen_svc.confirm_save(self._current_draft)
        self._current_draft = None
        self.save_button.setEnabled(False)
        self.status_label.setText(f"Saved to {path}")
