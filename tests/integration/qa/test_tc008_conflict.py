"""TC-008: Conflict evidence display.

Acceptance criteria:
- status == conflict
- conflict_sources >= 2 groups
- conflict sources reference different documents
"""

from opendocs.app.qa_service import QAService
from opendocs.qa.models import AnswerStatus


def test_conflict_detected_for_contradictory_budgets(conflict_qa_service: QAService) -> None:
    """Query about budget hits two conflicting documents."""
    response = conflict_qa_service.ask("项目预算")
    assert response.status == AnswerStatus.CONFLICT
    assert response.conflict_sources is not None
    assert len(response.conflict_sources) >= 1
    all_citations = [c for group in response.conflict_sources for c in group]
    doc_ids = {c.doc_id for c in all_citations}
    assert len(doc_ids) >= 2


def test_conflict_shows_multiple_sources(conflict_qa_service: QAService) -> None:
    """Conflict response includes citations from conflicting docs."""
    response = conflict_qa_service.ask("预算交付日期")
    assert response.status == AnswerStatus.CONFLICT
    assert len(response.citations) >= 2
    assert response.answer_text
