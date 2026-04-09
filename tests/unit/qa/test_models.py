"""Low-level fact and subject extraction invariants for S5."""

from __future__ import annotations

from opendocs.qa.models import extract_fact_records, extract_subject_terms


def test_structured_fact_line_has_single_owner_fact() -> None:
    records = extract_fact_records("Atlas 项目负责人：王敏")

    assert len(records) == 1
    assert records[0].key == "owner"
    assert records[0].value == "王敏"


def test_natural_fact_patterns_do_not_cross_match_other_keys() -> None:
    records = extract_fact_records("风险：供应商接口仍未稳定。")

    assert [record.key for record in records] == ["risk"]


def test_subject_terms_drop_grammatical_particles() -> None:
    subject_terms = extract_subject_terms("Nebula 项目的负责人是谁？")

    assert subject_terms == {"nebula"}
