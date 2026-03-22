"""SearchQAPage tests — search results, QA three-state display, citation jump."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from opendocs.qa.models import AnswerStatus, QAResponse
from opendocs.retrieval.evidence import Citation
from opendocs.ui.pages.search_qa_page import SearchQAPage


def test_search_populates_results(qtbot, mock_search_service, mock_qa_service):
    page = SearchQAPage(mock_search_service, mock_qa_service)
    qtbot.addWidget(page)

    page.query_input.setText("test query")
    page.search_button.click()

    mock_search_service.search.assert_called_once_with("test query")
    assert page.results_list.count() == 1


def test_empty_query_no_search(qtbot, mock_search_service, mock_qa_service):
    page = SearchQAPage(mock_search_service, mock_qa_service)
    qtbot.addWidget(page)

    page.query_input.setText("")
    page.search_button.click()

    mock_search_service.search.assert_not_called()


def test_qa_factual_displays_green(qtbot, mock_search_service, mock_qa_service):
    page = SearchQAPage(mock_search_service, mock_qa_service)
    qtbot.addWidget(page)

    page.query_input.setText("What is X?")
    page.ask_button.click()

    mock_qa_service.ask.assert_called_once_with("What is X?")
    assert "factual" in page.qa_status_label.text()
    assert "42" in page.qa_answer_text.toPlainText()
    assert page.qa_citations_list.count() == 1


def test_qa_insufficient_evidence(qtbot, mock_search_service, mock_qa_service):
    mock_qa_service.ask.return_value = QAResponse(
        status=AnswerStatus.INSUFFICIENT_EVIDENCE,
        answer_text="Cannot determine.",
        citations=[],
        checked_sources=[],
        next_steps=["Try broader search"],
        trace_id="t2",
    )

    page = SearchQAPage(mock_search_service, mock_qa_service)
    qtbot.addWidget(page)

    page.query_input.setText("Unknown topic?")
    page.ask_button.click()

    assert "insufficient" in page.qa_status_label.text()
    assert page.qa_conflict_label.isHidden() is True


def test_qa_conflict_shows_sources(qtbot, mock_search_service, mock_qa_service):
    cit_a = Citation(
        doc_id="d1", chunk_id="c1", path="/a.md",
        page_no=None, paragraph_range=None, char_range="0-50",
        quote_preview="Version A says X",
    )
    cit_b = Citation(
        doc_id="d2", chunk_id="c2", path="/b.md",
        page_no=None, paragraph_range=None, char_range="0-50",
        quote_preview="Version B says Y",
    )
    mock_qa_service.ask.return_value = QAResponse(
        status=AnswerStatus.CONFLICT,
        answer_text="Conflicting evidence.",
        citations=[cit_a, cit_b],
        checked_sources=[cit_a, cit_b],
        conflict_sources=[[cit_a], [cit_b]],
        trace_id="t3",
    )

    page = SearchQAPage(mock_search_service, mock_qa_service)
    qtbot.addWidget(page)

    page.query_input.setText("Conflicting topic?")
    page.ask_button.click()

    assert "conflict" in page.qa_status_label.text()
    assert not page.qa_conflict_label.isHidden()
    assert "/a.md" in page.qa_conflict_label.text()


def test_result_selection_loads_evidence(qtbot, mock_search_service, mock_qa_service):
    page = SearchQAPage(mock_search_service, mock_qa_service)
    qtbot.addWidget(page)

    page.query_input.setText("test")
    page.search_button.click()
    page.results_list.setCurrentRow(0)

    mock_search_service.locate_evidence.assert_called_once()
    assert page.evidence_panel.current_location is not None
