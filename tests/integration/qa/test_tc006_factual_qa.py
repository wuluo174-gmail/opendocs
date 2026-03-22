"""TC-006: Fact-based Q&A with citations.

Acceptance criteria:
- answer.citations non-empty
- key facts accepted by citation validator
- answer status is factual
"""

from opendocs.app.qa_service import QAService
from opendocs.qa.models import AnswerStatus


def test_factual_answer_has_citations(qa_service: QAService) -> None:
    """Single-doc factual Q&A returns citations."""
    # Use a query that hits only non-conflicting documents
    response = qa_service.ask("AI技术报告自然语言处理")
    assert response.status == AnswerStatus.FACTUAL
    assert len(response.citations) > 0
    assert response.trace_id


def test_factual_answer_citations_reference_real_chunks(qa_service: QAService) -> None:
    """Each citation points to a real chunk_id."""
    response = qa_service.ask("会议纪要团队负责人")
    assert response.status == AnswerStatus.FACTUAL
    for cit in response.citations:
        assert cit.chunk_id
        assert cit.path


def test_factual_answer_text_contains_cit_markers(qa_service: QAService) -> None:
    """MockProvider output includes [CIT:...] markers."""
    response = qa_service.ask("authentication module review")
    assert response.status == AnswerStatus.FACTUAL
    assert "[CIT:" in response.answer_text


def test_checked_sources_populated(qa_service: QAService) -> None:
    """checked_sources is always populated regardless of status."""
    response = qa_service.ask("会议纪要")
    assert len(response.checked_sources) > 0
