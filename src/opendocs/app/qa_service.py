"""Application-layer QA, summary, and insight service for S5."""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import select

from opendocs.app._audit_helpers import (
    build_file_audit_detail,
    build_text_input_audit_detail,
    create_audit_record,
    flush_audit_to_jsonl,
)
from opendocs.app.search_service import SearchService
from opendocs.domain.models import ChunkModel, DocumentModel
from opendocs.qa.citation_validator import CitationValidator
from opendocs.qa.conflict_detector import ConflictDetector
from opendocs.qa.generator import LocalExtractiveGenerator
from opendocs.qa.insight_extractor import InsightExtractor
from opendocs.qa.markdown_exporter import MarkdownExporter
from opendocs.qa.models import (
    ConflictSource,
    EvidenceBundle,
    EvidenceItem,
    ExportPreview,
    FactRecord,
    InsightResult,
    QAResult,
    QueryPlan,
    ResultPayload,
    SummaryResult,
    dedupe_citations,
    evidence_matches_subject,
    extract_evidence_units,
    extract_fact_records,
    format_source_label,
    iter_text_lines,
)
from opendocs.qa.orchestrator import QAOrchestrator
from opendocs.qa.summarizer import SummaryComposer
from opendocs.retrieval.evidence import Citation, build_citation
from opendocs.retrieval.filters import SearchFilter
from opendocs.storage.db import session_scope

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from opendocs.app.runtime import OpenDocsRuntime


class QAService:
    """Own the S5 answer, summary, insight, and markdown-export flow."""

    def __init__(
        self,
        runtime: OpenDocsRuntime,
        *,
        search_service: SearchService | None = None,
        orchestrator: QAOrchestrator | None = None,
        generator: LocalExtractiveGenerator | None = None,
        validator: CitationValidator | None = None,
        conflict_detector: ConflictDetector | None = None,
        summarizer: SummaryComposer | None = None,
        insight_extractor: InsightExtractor | None = None,
        exporter: MarkdownExporter | None = None,
    ) -> None:
        self._runtime = runtime
        self._engine = runtime.engine
        self._search = search_service or runtime.build_search_service()
        self._orchestrator = orchestrator or QAOrchestrator()
        self._generator = generator or LocalExtractiveGenerator()
        self._validator = validator or CitationValidator()
        self._conflict_detector = conflict_detector or ConflictDetector()
        self._summarizer = summarizer or SummaryComposer(self._generator)
        self._insight_extractor = insight_extractor or InsightExtractor()
        self._exporter = exporter or MarkdownExporter()

    def _ensure_runtime_open(self) -> None:
        self._runtime.ensure_open()

    def answer(
        self,
        question: str,
        *,
        filters: SearchFilter | None = None,
        top_k: int | None = None,
    ) -> QAResult:
        self._ensure_runtime_open()
        if not question or not question.strip():
            raise ValueError("question must not be empty")

        bundle = self._build_search_bundle(question, filters=filters, top_k=top_k)
        if not self._has_sufficient_evidence(bundle):
            result = self._build_insufficient_result(question, bundle)
            self._write_answer_audit(result)
            return result

        intent = bundle.query_plan.intent
        if intent == "summary":
            result = self._answer_via_summary_path(question, bundle)
        elif intent == "compare":
            result = self._answer_via_compare_path(question, bundle)
        elif intent == "timeline":
            result = self._answer_via_timeline_path(question, bundle)
        elif intent == "fact_list":
            result = self._answer_via_fact_list_path(question, bundle)
        else:
            result = self._answer_via_fact_path(question, bundle)

        self._write_answer_audit(result)
        return result

    def summarize(
        self,
        *,
        doc_ids: list[str] | None = None,
        query: str | None = None,
        filters: SearchFilter | None = None,
    ) -> SummaryResult:
        self._ensure_runtime_open()
        bundle = self._resolve_bundle_for_non_answer(doc_ids=doc_ids, query=query, filters=filters)
        result = self._summarizer.summarize(bundle)
        self._write_generation_audit(
            operation="answer_generate",
            target_type="generation",
            target_id=result.trace_id,
            result="success",
            detail_json=self._build_generation_detail(
                trace_id=result.trace_id,
                query=query,
                doc_ids=result.doc_ids,
                citation_count=len(result.citations),
                result_type=result.result_type,
            ),
        )
        return result

    def extract_insights(
        self,
        *,
        doc_ids: list[str] | None = None,
        query: str | None = None,
        filters: SearchFilter | None = None,
    ) -> InsightResult:
        self._ensure_runtime_open()
        bundle = self._resolve_bundle_for_non_answer(doc_ids=doc_ids, query=query, filters=filters)
        result = self._insight_extractor.extract(bundle)
        self._write_generation_audit(
            operation="answer_generate",
            target_type="generation",
            target_id=result.trace_id,
            result="success",
            detail_json=self._build_generation_detail(
                trace_id=result.trace_id,
                query=query,
                doc_ids=result.doc_ids,
                citation_count=len(result.citations),
                result_type=result.result_type,
            ),
        )
        return result

    def preview_markdown_export(self, result: ResultPayload, *, title: str) -> ExportPreview:
        self._ensure_runtime_open()
        return self._exporter.preview(result, title=title)

    def save_markdown_export(
        self,
        preview: ExportPreview,
        output_path: str | Path,
        *,
        confirmed: bool,
    ) -> Path:
        self._ensure_runtime_open()
        if not confirmed:
            raise ValueError("markdown export requires confirmed=True")
        target = Path(output_path).resolve()
        if target.exists():
            raise FileExistsError(
                f"refusing to overwrite existing file without an explicit new path: {target}"
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(preview.markdown, encoding="utf-8")
        self._write_generation_audit(
            operation="generation_export",
            target_type="generation",
            target_id=preview.trace_id,
            result="success",
            detail_json=build_file_audit_detail(
                target,
                title=preview.title,
                citation_count=len(preview.citations),
                format="markdown",
            ),
        )
        return target

    def _resolve_bundle_for_non_answer(
        self,
        *,
        doc_ids: list[str] | None,
        query: str | None,
        filters: SearchFilter | None,
    ) -> EvidenceBundle:
        if doc_ids:
            return self._build_document_bundle(doc_ids)
        if query and query.strip():
            return self._build_search_bundle(query, filters=filters, top_k=None)
        raise ValueError("either doc_ids or query must be provided")

    def _build_search_bundle(
        self,
        question: str,
        *,
        filters: SearchFilter | None,
        top_k: int | None,
    ) -> EvidenceBundle:
        response = self._search.search(question, filters=filters, top_k=top_k)
        previews = self._search.load_evidence_previews(
            [(result.doc_id, result.chunk_id) for result in response.results]
        )
        return self._orchestrator.build_bundle(
            question=question,
            response=response,
            previews=previews,
        )

    def _build_document_bundle(self, doc_ids: list[str]) -> EvidenceBundle:
        trace_id = str(uuid.uuid4())
        unique_doc_ids = list(dict.fromkeys(doc_ids))
        if not unique_doc_ids:
            return EvidenceBundle(
                query="selected documents",
                query_plan=QueryPlan(
                    question="selected documents",
                    intent="summary",
                    subject_terms=(),
                    requested_fact_keys=(),
                    requested_insight_kinds=(),
                ),
                trace_id=trace_id,
                items=[],
                total_candidates=0,
            )

        items: list[EvidenceItem] = []
        per_doc_count: dict[str, int] = {}
        with session_scope(self._engine) as session:
            statement = (
                select(
                    DocumentModel.doc_id,
                    DocumentModel.title,
                    DocumentModel.display_path,
                    DocumentModel.modified_at,
                    ChunkModel.chunk_id,
                    ChunkModel.chunk_index,
                    ChunkModel.text,
                    ChunkModel.char_start,
                    ChunkModel.char_end,
                    ChunkModel.page_no,
                    ChunkModel.paragraph_start,
                    ChunkModel.paragraph_end,
                    ChunkModel.heading_path,
                )
                .join(ChunkModel, ChunkModel.doc_id == DocumentModel.doc_id)
                .where(DocumentModel.doc_id.in_(tuple(unique_doc_ids)))
                .where(DocumentModel.is_deleted_from_fs.is_(False))
                .order_by(
                    DocumentModel.modified_at.desc(),
                    DocumentModel.doc_id.asc(),
                    ChunkModel.chunk_index.asc(),
                )
            )
            for row in session.execute(statement):
                doc_id = row.doc_id
                count = per_doc_count.get(doc_id, 0)
                if count >= 4:
                    continue
                per_doc_count[doc_id] = count + 1
                citation = build_citation(
                    doc_id=row.doc_id,
                    chunk_id=row.chunk_id,
                    path=row.display_path,
                    page_no=row.page_no,
                    paragraph_start=row.paragraph_start,
                    paragraph_end=row.paragraph_end,
                    char_start=row.char_start,
                    char_end=row.char_end,
                    text=row.text,
                    heading_path=row.heading_path,
                )
                summary = row.text[:200].replace("\n", " ").strip()
                if len(row.text) > 200:
                    summary += "..."
                units = extract_evidence_units(row.text)
                items.append(
                    EvidenceItem(
                        doc_id=row.doc_id,
                        chunk_id=row.chunk_id,
                        title=row.title,
                        path=row.display_path,
                        score=max(0.1, 1.0 - (count * 0.05)),
                        modified_at=row.modified_at,
                        summary=summary,
                        citation=citation,
                        preview_text=row.text,
                        units=units,
                        facts=extract_fact_records(row.text),
                    )
                )

        return EvidenceBundle(
            query="selected documents",
            query_plan=QueryPlan(
                question="selected documents",
                intent="summary",
                subject_terms=(),
                requested_fact_keys=(),
                requested_insight_kinds=(),
            ),
            trace_id=trace_id,
            items=items,
            total_candidates=len(items),
        )

    @staticmethod
    def _has_sufficient_evidence(bundle: EvidenceBundle) -> bool:
        return bool(bundle.items)

    def _answer_via_fact_path(self, question: str, bundle: EvidenceBundle) -> QAResult:
        if not bundle.query_plan.requested_fact_keys:
            return self._build_insufficient_result(question, bundle)

        conflict_sources = self._conflict_detector.detect(question, bundle)
        if len(conflict_sources) >= 2:
            return self._build_conflict_result(question, bundle, conflict_sources)

        draft = self._generator.generate_answer(question, bundle)
        validated = self._validator.validate(draft.statements)
        if not validated.statements:
            return self._build_insufficient_result(question, bundle)

        answer_lines = [statement.text for statement in validated.statements]
        citations = validated.citations
        uncertainty_notes = draft.uncertainty_notes or ["当前没有发现显式冲突，但仍建议核验原文。"]
        return self._build_answered_result(
            question,
            bundle,
            answer_lines=answer_lines,
            citations=citations,
            uncertainty_notes=uncertainty_notes,
        )

    def _answer_via_fact_list_path(
        self,
        question: str,
        bundle: EvidenceBundle,
    ) -> QAResult:
        distinct_entries = self._collect_distinct_relevant_fact_entries(bundle)
        if not distinct_entries:
            return self._build_insufficient_result(question, bundle)

        answer_lines = [fact.line_text for _, fact in distinct_entries[:6]]
        citations = dedupe_citations([item.citation for item, _ in distinct_entries[:6]])
        return self._build_answered_result(
            question,
            bundle,
            answer_lines=answer_lines,
            citations=citations,
            uncertainty_notes=["当前答案按结构化事实去重后展开。"],
        )

    def _answer_via_summary_path(self, question: str, bundle: EvidenceBundle) -> QAResult:
        requested_kinds = set(bundle.query_plan.requested_insight_kinds)
        if requested_kinds:
            insights = self._insight_extractor.extract(bundle, requested_kinds=requested_kinds)
            if not insights.items:
                return self._build_insufficient_result(question, bundle)
            answer_lines = [
                f"{self._insight_heading(item.kind)}：{item.text}" for item in insights.items
            ]
            return self._build_answered_result(
                question,
                bundle,
                answer_lines=answer_lines,
                citations=insights.citations,
                uncertainty_notes=["当前答案来自多文档汇总路径，建议继续核验引用原文。"],
            )

        summary = self._summarizer.summarize(bundle)
        if not summary.citations:
            return self._build_insufficient_result(question, bundle)
        answer_lines = [
            line.strip()[2:].strip()
            for line in summary.summary.splitlines()
            if line.strip().startswith("- ")
        ]
        if not answer_lines:
            return self._build_insufficient_result(question, bundle)
        return self._build_answered_result(
            question,
            bundle,
            answer_lines=answer_lines,
            citations=summary.citations,
            uncertainty_notes=["当前答案来自摘要路径，建议继续核验引用原文。"],
        )

    def _answer_via_compare_path(self, question: str, bundle: EvidenceBundle) -> QAResult:
        relevant_facts = self._collect_relevant_fact_entries(bundle)
        distinct_values = {fact.normalized_value for _, fact in relevant_facts}
        distinct_docs = {item.doc_id for item, _ in relevant_facts}
        if len(distinct_values) < 2 or len(distinct_docs) < 2:
            return self._build_insufficient_result(question, bundle)

        answer_lines = [
            f"{item.title}：{fact.raw_key} = {fact.value}" for item, fact in relevant_facts[:6]
        ]
        citations = dedupe_citations([item.citation for item, _ in relevant_facts[:6]])
        return self._build_answered_result(
            question,
            bundle,
            answer_lines=answer_lines,
            citations=citations,
            uncertainty_notes=["当前答案来自对比路径，差异已按来源展开。"],
        )

    def _answer_via_timeline_path(self, question: str, bundle: EvidenceBundle) -> QAResult:
        relevant_facts = self._collect_relevant_fact_entries(bundle)
        if not relevant_facts:
            timeline_lines = self._collect_timeline_lines(bundle)
            if len(timeline_lines) < 2:
                return self._build_insufficient_result(question, bundle)
            answer_lines = [
                f"{item.modified_at.strftime('%Y-%m-%d')}：{line}"
                for item, line in timeline_lines[:6]
            ]
            citations = dedupe_citations([item.citation for item, _ in timeline_lines[:6]])
        else:
            ordered = sorted(relevant_facts, key=lambda entry: entry[0].modified_at)
            if len(ordered) < 2:
                return self._build_insufficient_result(question, bundle)
            answer_lines = [
                f"{item.modified_at.strftime('%Y-%m-%d')}：{fact.line_text}"
                for item, fact in ordered[:6]
            ]
            citations = dedupe_citations([item.citation for item, _ in ordered[:6]])
        return self._build_answered_result(
            question,
            bundle,
            answer_lines=answer_lines,
            citations=citations,
            uncertainty_notes=["当前答案来自时间线路径，按文档时间顺序排列。"],
        )

    @staticmethod
    def _insight_heading(kind: str) -> str:
        return {
            "decision": "决策",
            "risk": "风险",
            "todo": "待办",
        }.get(kind, "洞察")

    def _collect_relevant_fact_entries(
        self,
        bundle: EvidenceBundle,
    ) -> list[tuple[EvidenceItem, FactRecord]]:
        requested_fact_keys = set(bundle.query_plan.requested_fact_keys)
        subject_terms = set(bundle.query_plan.subject_terms)
        entries: list[tuple[EvidenceItem, FactRecord]] = []
        for item in bundle.items:
            if not evidence_matches_subject(item, subject_terms):
                continue
            for fact in item.facts:
                if requested_fact_keys and fact.key not in requested_fact_keys:
                    continue
                entries.append((item, fact))
        return entries

    def _collect_distinct_relevant_fact_entries(
        self,
        bundle: EvidenceBundle,
    ) -> list[tuple[EvidenceItem, FactRecord]]:
        ordered_entries = sorted(
            self._collect_relevant_fact_entries(bundle),
            key=lambda entry: (
                entry[1].key,
                entry[0].modified_at,
                entry[1].normalized_value,
            ),
        )
        distinct_entries: list[tuple[EvidenceItem, FactRecord]] = []
        seen: set[tuple[str, str]] = set()
        for item, fact in ordered_entries:
            dedupe_key = (fact.key, fact.normalized_value)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            distinct_entries.append((item, fact))
        return distinct_entries

    @staticmethod
    def _collect_timeline_lines(bundle: EvidenceBundle) -> list[tuple[EvidenceItem, str]]:
        subject_terms = set(bundle.query_plan.subject_terms)
        timeline_lines: list[tuple[EvidenceItem, str]] = []
        for item in sorted(bundle.items, key=lambda evidence_item: evidence_item.modified_at):
            if not evidence_matches_subject(item, subject_terms):
                continue
            for line in iter_text_lines(item.preview_text):
                timeline_lines.append((item, line))
                break
        return timeline_lines

    def _build_answered_result(
        self,
        question: str,
        bundle: EvidenceBundle,
        *,
        answer_lines: list[str],
        citations: list[Citation],
        uncertainty_notes: list[str],
    ) -> QAResult:
        if not answer_lines or not citations:
            return self._build_insufficient_result(question, bundle)
        source_lines = [
            format_source_label(item.title, item.path)
            for item in bundle.items
            if any(
                citation.doc_id == item.doc_id and citation.chunk_id == item.chunk_id
                for citation in citations
            )
        ]
        answer = self._render_answer(answer_lines, source_lines, uncertainty_notes)
        return QAResult(
            question=question,
            trace_id=bundle.trace_id,
            result_type="answered",
            answer=answer,
            citations=dedupe_citations(list(citations)),
            checked_sources=self._checked_sources(bundle),
            uncertainty_notes=uncertainty_notes,
        )

    def _build_insufficient_result(self, question: str, bundle: EvidenceBundle) -> QAResult:
        checked_sources = self._checked_sources(bundle)
        answer = self._render_insufficient(checked_sources)
        return QAResult(
            question=question,
            trace_id=bundle.trace_id,
            result_type="insufficient_evidence",
            answer=answer,
            citations=[],
            checked_sources=checked_sources,
            suggested_next_steps=[
                "扩大检索范围",
                "指定时间范围 / 项目 / 目录",
            ],
        )

    def _build_conflict_result(
        self,
        question: str,
        bundle: EvidenceBundle,
        conflict_sources: list[ConflictSource],
    ) -> QAResult:
        citations = dedupe_citations([source.citation for source in conflict_sources])
        answer = self._render_conflict(conflict_sources)
        return QAResult(
            question=question,
            trace_id=bundle.trace_id,
            result_type="conflict",
            answer=answer,
            citations=citations,
            checked_sources=self._checked_sources(bundle),
            conflict_sources=conflict_sources,
            uncertainty_notes=["发现冲突信息，暂不输出单一结论。"],
            memory_conflict_note="若后续接入记忆，记忆可能陈旧或错误。",
        )

    @staticmethod
    def _checked_sources(bundle: EvidenceBundle) -> list[str]:
        return list(
            dict.fromkeys(format_source_label(item.title, item.path) for item in bundle.items)
        )

    @staticmethod
    def _render_answer(
        answer_lines: list[str],
        source_lines: list[str],
        uncertainty_notes: list[str],
    ) -> str:
        lines = ["结论："]
        lines.extend(f"- {line}" for line in answer_lines)
        lines.extend(["", "依据："])
        for index, source in enumerate(dict.fromkeys(source_lines), start=1):
            lines.append(f"{index}. 来源：{source}")
        lines.extend(["", "不确定性："])
        lines.extend(f"- {note}" for note in uncertainty_notes)
        return "\n".join(lines)

    @staticmethod
    def _render_insufficient(checked_sources: list[str]) -> str:
        lines = ["当前证据不足以可靠回答该问题。", "", "已检查来源："]
        if checked_sources:
            for index, source in enumerate(checked_sources[:5], start=1):
                lines.append(f"{index}. {source}")
        else:
            lines.append("1. 当前未检索到可用来源")
        lines.extend(
            [
                "",
                "建议下一步：",
                "- 扩大检索范围",
                "- 指定时间范围 / 项目 / 目录",
            ]
        )
        return "\n".join(lines)

    @staticmethod
    def _render_conflict(conflict_sources: list[ConflictSource]) -> str:
        lines = ["发现冲突信息，暂不输出单一结论。", ""]
        if conflict_sources:
            source_a = conflict_sources[0]
            lines.extend(
                [
                    "冲突来源 A：",
                    f"- {source_a.summary}",
                    f"- 来源：{format_source_label(source_a.title, source_a.path)}",
                    "",
                ]
            )
        if len(conflict_sources) > 1:
            source_b = conflict_sources[1]
            lines.extend(
                [
                    "冲突来源 B：",
                    f"- {source_b.summary}",
                    f"- 来源：{format_source_label(source_b.title, source_b.path)}",
                    "",
                ]
            )
        lines.extend(
            [
                "建议：",
                "- 由用户确认哪个版本为最新",
                "- 或查看时间更晚、级别更高的记录",
                "- 若后续接入记忆，记忆可能陈旧或错误",
            ]
        )
        return "\n".join(lines)

    def _write_answer_audit(self, result: QAResult) -> None:
        detail = build_text_input_audit_detail(
            result.question,
            field_name="question",
            result_type=result.result_type,
            citation_count=len(result.citations),
            checked_source_count=len(result.checked_sources),
        )
        self._write_generation_audit(
            operation="answer_generate",
            target_type="answer",
            target_id=result.trace_id,
            result="success",
            detail_json=detail,
        )

    @staticmethod
    def _build_generation_detail(
        *,
        trace_id: str,
        query: str | None,
        doc_ids: list[str],
        citation_count: int,
        result_type: str,
    ) -> dict[str, object]:
        detail: dict[str, object]
        if query:
            detail = build_text_input_audit_detail(
                query,
                field_name="query",
                result_type=result_type,
            )
        else:
            detail = {
                "result_type": result_type,
            }
        detail.update(
            {
                "trace_id": trace_id,
                "doc_count": len(doc_ids),
                "citation_count": citation_count,
            }
        )
        return detail

    def _write_generation_audit(
        self,
        *,
        operation: str,
        target_type: str,
        target_id: str,
        result: str,
        detail_json: dict[str, object],
    ) -> None:
        try:
            with session_scope(self._engine) as session:
                audit = create_audit_record(
                    session,
                    actor="system",
                    operation=operation,
                    target_type=target_type,
                    target_id=target_id,
                    result=result,
                    detail_json=detail_json,
                    trace_id=target_id,
                )
            flush_audit_to_jsonl(audit)
        except Exception:
            logger.debug("Failed to write QA audit", exc_info=True)
