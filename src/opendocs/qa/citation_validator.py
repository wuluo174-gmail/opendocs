"""Citation validator — verify LLM output references real evidence."""

from __future__ import annotations

import re

from opendocs.qa.models import ValidationResult

_CIT_PATTERN = re.compile(r"\[CIT:([^\]]+)\]")


class CitationValidator:
    """Validate that every [CIT:chunk_id] in LLM output exists in the evidence package."""

    def validate(
        self,
        answer_text: str,
        chunk_texts: dict[str, str],
    ) -> ValidationResult:
        cited_ids = _CIT_PATTERN.findall(answer_text)
        valid_ids = [cid for cid in cited_ids if cid in chunk_texts]
        invalid_ids = [cid for cid in cited_ids if cid not in chunk_texts]

        return ValidationResult(
            valid=len(invalid_ids) == 0 and len(valid_ids) > 0,
            cited_chunk_ids=valid_ids,
            invalid_chunk_ids=invalid_ids,
        )


def strip_invalid_citations(answer_text: str, invalid_ids: list[str]) -> str:
    """Remove invalid [CIT:...] markers from answer text."""
    for cid in invalid_ids:
        answer_text = answer_text.replace(f"[CIT:{cid}]", "")
    return answer_text
