"""GenerationPage tests — generate draft, save with confirmation."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from opendocs.ui.pages.generation_page import GenerationPage


def test_generate_populates_draft(qtbot, mock_generation_service):
    page = GenerationPage(mock_generation_service)
    qtbot.addWidget(page)

    page.query_input.setText("monthly report")
    page.generate_button.click()

    mock_generation_service.generate.assert_called_once()
    assert "Draft content" in page.draft_editor.toPlainText()
    assert page.citations_list.count() == 1
    assert page.save_button.isEnabled()


def test_save_requires_confirmation(qtbot, mock_generation_service):
    page = GenerationPage(mock_generation_service)
    qtbot.addWidget(page)

    page.query_input.setText("monthly report")
    page.generate_button.click()

    with patch("opendocs.ui.pages.generation_page.ConfirmDialog") as dialog_cls:
        dialog_cls.return_value.exec.return_value = 1  # QDialog.Accepted
        page.save_button.click()

    mock_generation_service.confirm_save.assert_called_once()
    assert not page.save_button.isEnabled()


def test_save_cancelled_keeps_draft(qtbot, mock_generation_service):
    page = GenerationPage(mock_generation_service)
    qtbot.addWidget(page)

    page.query_input.setText("monthly report")
    page.generate_button.click()

    with patch("opendocs.ui.pages.generation_page.ConfirmDialog") as dialog_cls:
        dialog_cls.return_value.exec.return_value = 0  # QDialog.Rejected
        page.save_button.click()

    mock_generation_service.confirm_save.assert_not_called()
    assert page.save_button.isEnabled()


def test_template_combo_populated(qtbot, mock_generation_service):
    page = GenerationPage(mock_generation_service)
    qtbot.addWidget(page)

    assert page.template_combo.count() == 3  # (auto) + 2 templates
