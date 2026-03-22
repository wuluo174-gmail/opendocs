"""ArchivePage tests — plan preview, approve, execute with confirmation, rollback."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from opendocs.domain.models import FileOperationPlanModel
from opendocs.ui.pages.archive_page import ArchivePage


@pytest.fixture()
def archive_page(mock_archive_service, qtbot):
    mock_archive_service.classify_and_plan.return_value = "plan-001"
    plan = MagicMock(spec=FileOperationPlanModel)
    plan.preview_json = {
        "items": [
            {
                "doc_id": "d1",
                "source_path": "/docs/a.md",
                "target_path": "/archive/2026/a.md",
                "operation_type": "move",
                "conflict": False,
            },
        ],
    }
    mock_archive_service.get_plan.return_value = plan

    page = ArchivePage(mock_archive_service)
    qtbot.addWidget(page)
    return page


def test_plan_populates_preview(archive_page, mock_archive_service):
    archive_page.doc_ids_input.setText("d1")
    archive_page.archive_dir_input.setText("/archive")
    archive_page.plan_button.click()

    mock_archive_service.classify_and_plan.assert_called_once()
    assert archive_page.preview_table.rowCount() == 1
    assert archive_page.approve_button.isEnabled()
    assert not archive_page.execute_button.isEnabled()


def test_approve_enables_execute(archive_page, mock_archive_service):
    archive_page.doc_ids_input.setText("d1")
    archive_page.archive_dir_input.setText("/archive")
    archive_page.plan_button.click()
    archive_page.approve_button.click()

    mock_archive_service.approve.assert_called_once_with("plan-001")
    assert archive_page.execute_button.isEnabled()
    assert not archive_page.approve_button.isEnabled()


def test_execute_requires_confirmation(archive_page, mock_archive_service):
    archive_page.doc_ids_input.setText("d1")
    archive_page.archive_dir_input.setText("/archive")
    archive_page.plan_button.click()
    archive_page.approve_button.click()

    with patch("opendocs.ui.pages.archive_page.ConfirmDialog") as dialog_cls:
        dialog_cls.return_value.exec.return_value = 0  # Rejected
        archive_page.execute_button.click()

    mock_archive_service.execute.assert_not_called()


def test_rollback_requires_confirmation(archive_page, mock_archive_service):
    with patch("opendocs.ui.pages.archive_page.ConfirmDialog") as dialog_cls:
        dialog_cls.return_value.exec.return_value = 0  # Rejected
        archive_page.rollback_button.click()

    mock_archive_service.rollback_last_batch.assert_not_called()
