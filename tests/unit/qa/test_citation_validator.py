"""Unit tests for CitationValidator."""

from opendocs.qa.citation_validator import CitationValidator, strip_invalid_citations


def test_valid_citations():
    v = CitationValidator()
    text = "结论A [CIT:c1] 结论B [CIT:c2]"
    result = v.validate(text, {"c1": "text1", "c2": "text2"})
    assert result.valid
    assert result.cited_chunk_ids == ["c1", "c2"]
    assert result.invalid_chunk_ids == []


def test_invalid_citation():
    v = CitationValidator()
    text = "结论A [CIT:c1] 结论B [CIT:missing]"
    result = v.validate(text, {"c1": "text1"})
    assert not result.valid
    assert result.cited_chunk_ids == ["c1"]
    assert result.invalid_chunk_ids == ["missing"]


def test_no_citations():
    v = CitationValidator()
    result = v.validate("无引用的回答", {"c1": "text"})
    assert not result.valid
    assert result.cited_chunk_ids == []


def test_strip_invalid():
    text = "结论A [CIT:c1] 结论B [CIT:bad]"
    stripped = strip_invalid_citations(text, ["bad"])
    assert "[CIT:c1]" in stripped
    assert "[CIT:bad]" not in stripped
