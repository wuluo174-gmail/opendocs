"""TC-012: Generate monthly report draft from historical documents.

Acceptance criteria (from acceptance_cases.md):
- Draft can be generated from template
- Editable before save
- Save requires explicit confirmation
- Output file contains citation block or footnotes
"""

from __future__ import annotations

import pytest

from opendocs.app.generation_service import GenerationService
from opendocs.storage.db import session_scope
from opendocs.storage.repositories import AuditRepository


def test_generate_monthly_report(generation_service: GenerationService) -> None:
    draft = generation_service.generate(
        "项目进度",
        template_name="monthly_report",
        template_vars={"report_period": "2026-03"},
    )
    assert draft.content
    assert len(draft.citations) > 0
    assert not draft.saved
    assert draft.template_name == "monthly_report"
    assert draft.trace_id


def test_draft_editable_before_save(generation_service: GenerationService) -> None:
    draft = generation_service.generate(
        "项目进度",
        template_name="monthly_report",
        template_vars={"report_period": "2026-03"},
    )
    original = draft.content
    edited = generation_service.edit_draft(draft, original + "\n\n## 补充说明\n测试编辑内容")
    assert "补充说明" in edited.content
    assert edited is draft


def test_confirm_save_creates_file(generation_service: GenerationService) -> None:
    draft = generation_service.generate(
        "项目进度",
        template_name="monthly_report",
        template_vars={"report_period": "2026-03"},
    )
    generation_service.edit_draft(draft, draft.content + "\n\n## 编辑区\n已编辑")
    output_path = generation_service.confirm_save(draft)

    assert output_path.exists()
    content = output_path.read_text(encoding="utf-8")
    assert "CIT:" in content
    assert draft.saved is True
    assert output_path.name.startswith("monthly_report_")


def test_save_audit_recorded(
    generation_service: GenerationService,
    generation_indexed_env: tuple,
) -> None:
    engine = generation_indexed_env[0]
    draft = generation_service.generate(
        "项目进度",
        template_name="weekly_report",
        template_vars={"week_label": "第12周"},
    )
    generation_service.confirm_save(draft)

    with session_scope(engine) as session:
        repo = AuditRepository(session)
        logs = repo.query(trace_id=draft.trace_id)
        save_logs = [l for l in logs if l.operation == "draft_save"]
        assert len(save_logs) >= 1
        assert save_logs[0].target_id == draft.draft_id


def test_edit_after_save_raises(generation_service: GenerationService) -> None:
    draft = generation_service.generate(
        "项目进度",
        template_name="monthly_report",
        template_vars={"report_period": "2026-03"},
    )
    generation_service.confirm_save(draft)
    with pytest.raises(ValueError, match="cannot edit a saved draft"):
        generation_service.edit_draft(draft, "new content")


def test_double_save_raises(generation_service: GenerationService) -> None:
    draft = generation_service.generate(
        "项目进度",
        template_name="monthly_report",
        template_vars={"report_period": "2026-03"},
    )
    generation_service.confirm_save(draft)
    with pytest.raises(ValueError, match="draft already saved"):
        generation_service.confirm_save(draft)


def test_free_form_generation(generation_service: GenerationService) -> None:
    draft = generation_service.generate(
        "项目风险",
        free_form_instruction="请列出所有风险项，每条引用来源 [CIT:chunk_id]。",
    )
    assert draft.content
    assert draft.template_name is None
    assert len(draft.citations) > 0


def test_list_templates(generation_service: GenerationService) -> None:
    templates = generation_service.list_templates()
    expected = {
        "meeting_minutes",
        "monthly_report",
        "project_summary",
        "retrospective",
        "risk_checklist",
        "weekly_report",
    }
    assert set(templates) == expected


def test_generate_does_not_create_file(generation_service: GenerationService) -> None:
    draft = generation_service.generate(
        "项目进度",
        template_name="monthly_report",
        template_vars={"report_period": "2026-03"},
    )
    prefix = draft.template_name or "draft"
    expected_name = f"{prefix}_{draft.draft_id[:8]}.md"
    output_dir = generation_service._output_dir
    assert not (output_dir / expected_name).exists()
