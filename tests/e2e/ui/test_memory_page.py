"""MemoryPage tests — recall, correct, disable."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from opendocs.ui.pages.memory_page import MemoryPage


@pytest.fixture()
def memory_page(mock_memory_service, qtbot):
    page = MemoryPage(mock_memory_service)
    qtbot.addWidget(page)
    return page


def test_recall_populates_table(memory_page, mock_memory_service):
    mem = MagicMock()
    mem.memory_id = "m1"
    mem.key = "project_status"
    mem.memory_type = "M1"
    mem.status = "active"
    mem.content = "Project is on track"
    mock_memory_service.recall.return_value = [mem]

    memory_page.scope_type_combo.setCurrentText("task")
    memory_page.scope_id_input.setText("task-1")
    memory_page.recall_button.click()

    mock_memory_service.recall.assert_called_once_with(scope_type="task", scope_id="task-1")
    assert memory_page.memory_table.rowCount() == 1


def test_empty_scope_id_shows_error(memory_page, mock_memory_service):
    memory_page.scope_id_input.setText("")
    memory_page.recall_button.click()

    mock_memory_service.recall.assert_not_called()
    assert "required" in memory_page.status_label.text().lower()


def test_disable_calls_service(memory_page, mock_memory_service):
    mem = MagicMock()
    mem.memory_id = "m1"
    mem.key = "test_key"
    mem.memory_type = "M0"
    mem.status = "active"
    mem.content = "content"
    mock_memory_service.recall.return_value = [mem]
    mock_memory_service.get.return_value = mem

    memory_page.scope_id_input.setText("s1")
    memory_page.recall_button.click()
    memory_page.memory_table.setCurrentCell(0, 0)
    memory_page.disable_button.click()

    mock_memory_service.disable.assert_called_once()
    assert not memory_page.disable_button.isEnabled()
