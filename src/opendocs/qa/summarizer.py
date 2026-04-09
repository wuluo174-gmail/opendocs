"""Summary assembly for S5."""

from __future__ import annotations

from opendocs.qa.generator import LocalExtractiveGenerator
from opendocs.qa.models import EvidenceBundle, SummaryResult, dedupe_citations


class SummaryComposer:
    """Build source-traceable summaries from an evidence bundle."""

    def __init__(self, generator: LocalExtractiveGenerator | None = None) -> None:
        self._generator = generator or LocalExtractiveGenerator()

    def summarize(self, bundle: EvidenceBundle) -> SummaryResult:
        draft = self._generator.generate_summary(bundle)
        citations = dedupe_citations([line.evidence.citation for line in draft.lines])
        summary_lines = [f"- {line.text}" for line in draft.lines]
        if not summary_lines:
            summary_lines.append("- 当前未提取到稳定摘要，请检查检索范围。")
        return SummaryResult(
            trace_id=bundle.trace_id,
            result_type="summary",
            summary="\n".join(summary_lines),
            citations=citations,
            source_count=len({item.doc_id for item in bundle.items}),
            doc_ids=list({item.doc_id for item in bundle.items}),
        )
