"""SettingsPage tests — add source, trigger indexing."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from opendocs.ui.pages.settings_page import SettingsPage


def test_add_button_calls_add_source(qtbot, mock_source_service, mock_index_service):
    mock_source = MagicMock()
    mock_source.source_root_id = "src-1"
    mock_source_service.add_source.return_value = mock_source

    page = SettingsPage(mock_source_service, mock_index_service)
    qtbot.addWidget(page)

    page.path_input.setText("/tmp/docs")

    with patch("opendocs.ui.pages.settings_page._IndexWorker") as worker_cls:
        worker_mock = MagicMock()
        worker_cls.return_value = worker_mock
        page.add_button.click()

    mock_source_service.add_source.assert_called_once_with("/tmp/docs")


def test_empty_path_shows_error(qtbot, mock_source_service, mock_index_service):
    page = SettingsPage(mock_source_service, mock_index_service)
    qtbot.addWidget(page)

    page.path_input.setText("")
    page.add_button.click()

    assert "empty" in page.status_label.text().lower()
    mock_source_service.add_source.assert_not_called()


def test_source_list_populated(qtbot, mock_source_service, mock_index_service):
    src = MagicMock()
    src.label = "My Docs"
    src.path = "/tmp/docs"
    src.source_root_id = "12345678-abcd"
    mock_source_service.list_sources.return_value = [src]

    page = SettingsPage(mock_source_service, mock_index_service)
    qtbot.addWidget(page)

    assert page.source_list.count() == 1
    assert "My Docs" in page.source_list.item(0).text()
