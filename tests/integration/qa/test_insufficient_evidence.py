"""S5 TC-007 insufficient-evidence coverage."""

from __future__ import annotations

import pytest

from opendocs.app.qa_service import QAService


@pytest.mark.parametrize(
    "question",
    [
        "Nebula 项目的预算是多少？",
        "Nebula 项目的负责人是谁？",
        "Nebula 项目的发布时间是什么时候？",
        "Nebula 项目使用了哪家供应商？",
        "Nebula 项目的合同编号是多少？",
        "Atlas 项目的合同编号是多少？",
    ],
)
def test_insufficient_evidence_refuses_to_guess(
    qa_service: QAService,
    question: str,
) -> None:
    result = qa_service.answer(question)

    assert result.result_type == "insufficient_evidence"
    assert not result.citations
    assert "当前证据不足以可靠回答该问题。" in result.answer
    assert "建议下一步：" in result.answer
    assert "Nebula" not in result.answer
