"""Decision/risk/todo extraction for S5."""

from __future__ import annotations

from opendocs.qa.models import (
    EvidenceBundle,
    InsightItem,
    InsightResult,
    clean_insight_text,
    dedupe_citations,
)

_ORDER = {
    "decision": 0,
    "risk": 1,
    "todo": 2,
}


class InsightExtractor:
    """Extract structured insights from explicit evidence lines."""

    def extract(
        self,
        bundle: EvidenceBundle,
        *,
        requested_kinds: set[str] | None = None,
    ) -> InsightResult:
        items: list[InsightItem] = []
        for evidence in bundle.items:
            for unit in evidence.units:
                if not unit.insight_kinds:
                    continue
                cleaned_text = clean_insight_text(unit.text)
                if not cleaned_text:
                    continue
                for matched_kind in unit.insight_kinds:
                    if requested_kinds is not None and matched_kind not in requested_kinds:
                        continue
                    items.append(
                        InsightItem(
                            kind=matched_kind,
                            text=cleaned_text,
                            source_title=evidence.title,
                            source_path=evidence.path,
                            citations=[evidence.citation],
                        )
                    )

        items = self._dedupe_items(items)
        citations = dedupe_citations([citation for item in items for citation in item.citations])
        overview = (
            f"共提取 {sum(item.kind == 'decision' for item in items)} 条决策、"
            f"{sum(item.kind == 'risk' for item in items)} 条风险、"
            f"{sum(item.kind == 'todo' for item in items)} 条待办。"
        )
        return InsightResult(
            trace_id=bundle.trace_id,
            result_type="insights",
            overview=overview,
            items=items,
            citations=citations,
            source_count=len({item.doc_id for item in bundle.items}),
            doc_ids=list({item.doc_id for item in bundle.items}),
        )

    @staticmethod
    def _dedupe_items(items: list[InsightItem]) -> list[InsightItem]:
        ordered = sorted(items, key=lambda item: (_ORDER[item.kind], item.text))
        deduped: list[InsightItem] = []
        seen: set[tuple[str, str]] = set()
        for item in ordered:
            key = (item.kind, item.text.casefold())
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped
