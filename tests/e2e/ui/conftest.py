"""Shared fixtures for e2e UI tests — mock services + offscreen Qt."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from opendocs.app.archive_service import ArchiveService
from opendocs.app.generation_service import GenerationService
from opendocs.app.index_service import IndexService
from opendocs.app.qa_service import QAService
from opendocs.app.search_service import SearchService
from opendocs.app.source_service import SourceService
from opendocs.app.summary_service import SummaryService
from opendocs.generation.models import Draft, SummaryResponse
from opendocs.memory.service import MemoryService
from opendocs.qa.models import AnswerStatus, QAResponse
from opendocs.retrieval.evidence import Citation, SearchResponse, SearchResult
from opendocs.retrieval.rerank import ScoreBreakdown
from opendocs.retrieval.evidence_locator import EvidenceLocation


def _make_citation(**overrides: object) -> Citation:
    defaults = dict(
        doc_id="d1",
        chunk_id="c1",
        path="/docs/test.md",
        page_no=None,
        paragraph_range="1-2",
        char_range="0-100",
        quote_preview="sample quote",
    )
    defaults.update(overrides)
    return Citation(**defaults)


def _make_search_result(**overrides: object) -> SearchResult:
    defaults = dict(
        chunk_id="c1",
        doc_id="d1",
        title="Test Doc",
        path="/docs/test.md",
        summary="A test document",
        modified_at=datetime(2026, 1, 1),
        score=0.85,
        score_breakdown=ScoreBreakdown(
            lexical_raw=-1.0, lexical_normalized=0.5,
            dense_raw=0.3, dense_normalized=0.3,
            freshness_boost=0.05, hybrid_score=0.85,
        ),
        citation=_make_citation(),
    )
    defaults.update(overrides)
    return SearchResult(**defaults)


@pytest.fixture()
def mock_source_service() -> MagicMock:
    svc = MagicMock(spec=SourceService)
    svc.list_sources.return_value = []
    return svc


@pytest.fixture()
def mock_index_service() -> MagicMock:
    return MagicMock(spec=IndexService)


@pytest.fixture()
def mock_search_service() -> MagicMock:
    svc = MagicMock(spec=SearchService)
    svc.search.return_value = SearchResponse(
        query="test",
        results=[_make_search_result()],
        total_candidates=1,
        trace_id="t1",
        duration_sec=0.01,
        filters_applied=None,
    )
    svc.locate_evidence.return_value = EvidenceLocation(
        path="/docs/test.md",
        page_no=None,
        paragraph_range="1-2",
        char_range="0-100",
        quote_preview="sample quote",
        can_open=True,
    )
    return svc


@pytest.fixture()
def mock_qa_service() -> MagicMock:
    svc = MagicMock(spec=QAService)
    svc.ask.return_value = QAResponse(
        status=AnswerStatus.FACTUAL,
        answer_text="The answer is 42.",
        citations=[_make_citation()],
        checked_sources=[_make_citation()],
        trace_id="t1",
    )
    return svc


@pytest.fixture()
def mock_summary_service() -> MagicMock:
    svc = MagicMock(spec=SummaryService)
    svc.summarize.return_value = SummaryResponse(
        summary_text="Summary text",
        insights=[],
        source_doc_ids=["d1"],
        citations=[_make_citation()],
        trace_id="t1",
        duration_sec=0.01,
    )
    svc.export.return_value = "# Summary\n\nSummary text"
    return svc


@pytest.fixture()
def mock_generation_service() -> MagicMock:
    svc = MagicMock(spec=GenerationService)
    svc.list_templates.return_value = ["monthly_report", "meeting_notes"]
    svc.generate.return_value = Draft(
        draft_id="draft-1",
        template_name="monthly_report",
        content="Draft content here.",
        citations=[_make_citation()],
        source_doc_ids=["d1"],
        trace_id="t1",
        created_at=datetime(2026, 1, 1),
    )
    svc.edit_draft.side_effect = lambda draft, new_content: Draft(
        draft_id=draft.draft_id,
        template_name=draft.template_name,
        content=new_content,
        citations=draft.citations,
        source_doc_ids=draft.source_doc_ids,
        trace_id=draft.trace_id,
        created_at=draft.created_at,
    )
    svc.confirm_save.return_value = "/tmp/output/draft.md"
    return svc


@pytest.fixture()
def mock_archive_service() -> MagicMock:
    return MagicMock(spec=ArchiveService)


@pytest.fixture()
def mock_memory_service() -> MagicMock:
    svc = MagicMock(spec=MemoryService)
    svc.recall.return_value = []
    return svc
