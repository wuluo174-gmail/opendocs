"""TC-007: Evidence insufficiency refusal.

Acceptance criteria:
- status == insufficient_evidence
- no unsupported conclusions (no hallucinated facts)
- next_steps provided
"""

from pathlib import Path

from sqlalchemy.engine import Engine

from opendocs.app.qa_service import QAService
from opendocs.provider.mock import MockProvider
from opendocs.qa.models import AnswerStatus


def test_insufficient_for_unknown_topic(
    qa_indexed_env: tuple[Engine, Path],
    qa_hnsw_path: Path,
) -> None:
    """Query with very high min_score returns insufficient."""
    engine, _ = qa_indexed_env
    strict_service = QAService(
        engine,
        hnsw_path=qa_hnsw_path,
        provider=MockProvider(),
        min_evidence=1,
        min_score=0.99,
    )
    response = strict_service.ask("量子计算在生物医学中的突破性应用")
    assert response.status == AnswerStatus.INSUFFICIENT_EVIDENCE
    assert len(response.citations) == 0
    assert response.next_steps is not None
    assert len(response.next_steps) > 0


def test_insufficient_no_hallucination(
    qa_indexed_env: tuple[Engine, Path],
    qa_hnsw_path: Path,
) -> None:
    """Insufficient response text uses template, not LLM generation."""
    engine, _ = qa_indexed_env
    strict_service = QAService(
        engine,
        hnsw_path=qa_hnsw_path,
        provider=MockProvider(),
        min_evidence=1,
        min_score=0.99,
    )
    response = strict_service.ask("量子纠缠态的宏观表现")
    assert response.status == AnswerStatus.INSUFFICIENT_EVIDENCE
    assert "证据不足" in response.answer_text
    assert "建议下一步" in response.answer_text
