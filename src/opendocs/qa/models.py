"""QA data contracts and structured fact/query helpers for S5."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from opendocs.retrieval.evidence import Citation

QueryIntent = Literal["fact", "fact_list", "summary", "compare", "timeline"]
QAResultType = Literal["answered", "insufficient_evidence", "conflict"]
InsightKind = Literal["decision", "risk", "todo"]
FactKey = Literal[
    "project_name",
    "owner",
    "publish_time",
    "status",
    "phase",
    "budget",
    "vendor",
    "contract_no",
    "decision",
    "risk",
    "todo",
]

_CJK_RE = re.compile(r"[\u4e00-\u9fff]+")
_WORD_RE = re.compile(r"[a-z0-9]+")
_SPACE_RE = re.compile(r"\s+")
_FACT_LINE_RE = re.compile(r"^(?P<key>[^:：]{1,80})[:：]\s*(?P<value>.+)$")
_GENERIC_TERMS = {
    "什么",
    "多少",
    "是否",
    "谁",
    "何时",
    "哪里",
    "如何",
    "为什么",
    "情况",
    "项目",
    "文档",
    "请问",
    "一下",
    "告诉",
    "说明",
    "介绍",
    "当前",
    "最新",
    "是多少",
    "是谁",
    "哪些",
    "列出",
}
_ATTRIBUTE_TERMS = {
    "负责人",
    "发布",
    "发布时间",
    "日期",
    "预算",
    "供应商",
    "合同",
    "合同编号",
    "决策",
    "风险",
    "待办",
    "行动项",
    "状态",
    "阶段",
    "关键",
    "时间线",
    "时间轴",
    "比较",
    "对比",
}
_COMPARE_REQUEST_TERMS = ("对比", "比较", "compare")
_TIMELINE_REQUEST_TERMS = ("时间线", "时间轴", "timeline")
_SUMMARY_REQUEST_TERMS = ("总结", "摘要", "汇总", "summarize", "summary")
_ENUMERATION_REQUEST_TERMS = ("列出", "哪些", "有哪些", "列表", "清单")
_FACT_KEY_ALIASES: tuple[tuple[FactKey, tuple[str, ...]], ...] = (
    ("contract_no", ("合同编号", "合同号", "contractno", "contract number")),
    ("publish_time", ("发布时间", "发布日期", "上线时间", "release date", "publish time")),
    ("owner", ("项目负责人", "负责人", "owner")),
    ("budget", ("项目预算", "预算", "budget")),
    ("vendor", ("供应商", "合作方", "vendor")),
    ("status", ("项目状态", "状态", "status")),
    ("phase", ("项目阶段", "阶段", "phase")),
    ("project_name", ("项目名称", "名称", "project name")),
    ("decision", ("关键决策", "决策", "决定", "decision")),
    ("risk", ("风险项", "关键风险", "风险", "risk")),
    ("todo", ("行动项", "待办", "todo", "action")),
)
_ATTRIBUTE_ALIAS_INDEX: dict[FactKey, tuple[str, ...]] = {
    fact_key: aliases for fact_key, aliases in _FACT_KEY_ALIASES
}
_VALUE_FRAGMENT = r"(?P<value>[^，。；;]+)"
_NATURAL_FACT_PATTERNS: tuple[tuple[FactKey, str, re.Pattern[str]], ...] = (
    (
        "owner",
        "项目负责人",
        re.compile(
            rf"(?P<subject>[a-z0-9\u4e00-\u9fff_-]+)\s*项目(?:的)?负责人(?:是|为|[:：])\s*{_VALUE_FRAGMENT}",
            re.IGNORECASE,
        ),
    ),
    (
        "publish_time",
        "发布时间",
        re.compile(
            r"(?:发布时间|发布日期|上线时间)(?:是|为|[:：])\s*"
            r"(?P<value>\d{4}(?:[-/年])\d{1,2}(?:[-/月])\d{1,2}日?)",
            re.IGNORECASE,
        ),
    ),
    (
        "budget",
        "预算",
        re.compile(
            rf"(?:项目预算|预算)(?:是|为|[:：])\s*{_VALUE_FRAGMENT}",
            re.IGNORECASE,
        ),
    ),
    (
        "vendor",
        "供应商",
        re.compile(
            rf"(?:供应商|合作方)(?:是|为|[:：])\s*{_VALUE_FRAGMENT}",
            re.IGNORECASE,
        ),
    ),
    (
        "contract_no",
        "合同编号",
        re.compile(
            r"(?:合同编号|合同号)(?:是|为|[:：])\s*(?P<value>[a-z0-9._-]+)",
            re.IGNORECASE,
        ),
    ),
    (
        "phase",
        "项目阶段",
        re.compile(
            rf"(?:项目阶段|阶段)(?:是|为|[:：])\s*{_VALUE_FRAGMENT}",
            re.IGNORECASE,
        ),
    ),
    (
        "status",
        "项目状态",
        re.compile(
            rf"(?:项目状态|状态)(?:是|为|[:：])\s*{_VALUE_FRAGMENT}",
            re.IGNORECASE,
        ),
    ),
)
_INSIGHT_PREFIXES: dict[InsightKind, tuple[str, ...]] = {
    "decision": ("决策:", "决策：", "决定:", "决定：", "decision:"),
    "risk": ("风险:", "风险：", "风险项:", "风险项：", "risk:"),
    "todo": ("待办:", "待办：", "行动项:", "行动项：", "todo:", "action:"),
}
_INSIGHT_PATTERNS: dict[InsightKind, tuple[re.Pattern[str], ...]] = {
    "decision": (re.compile(r"(?:决定|决议|确定|采用|冻结|统一使用|开放|不再)", re.IGNORECASE),),
    "risk": (re.compile(r"(?:风险|不稳定|冲突|延期|抖动|误判)", re.IGNORECASE),),
    "todo": (re.compile(r"(?:待办|行动项|需要|需|补齐|准备|梳理|整理|限制)", re.IGNORECASE),),
}


def normalize_text(text: str) -> str:
    """Normalize free text for local extractive matching."""
    lowered = text.casefold().replace("：", ":")
    stripped = re.sub(r"[^\w\u4e00-\u9fff:.-]+", " ", lowered)
    return _SPACE_RE.sub(" ", stripped).strip()


def normalize_fact_value(value: str) -> str:
    """Normalize a fact value for equality checks across evidence sources."""
    return normalize_text(value).replace(" ", "")


def extract_terms(text: str) -> set[str]:
    """Extract lightweight search terms without external NLP dependencies."""
    normalized = normalize_text(text)
    terms: set[str] = set()

    for match in _WORD_RE.findall(normalized):
        if len(match) >= 2 and match not in _GENERIC_TERMS:
            terms.add(match)

    for block in _CJK_RE.findall(normalized):
        if len(block) >= 2 and block not in _GENERIC_TERMS:
            terms.add(block)
        if len(block) >= 2:
            for index in range(len(block) - 1):
                token = block[index : index + 2]
                if token not in _GENERIC_TERMS:
                    terms.add(token)
        if len(block) >= 3:
            for index in range(len(block) - 2):
                token = block[index : index + 3]
                if token not in _GENERIC_TERMS:
                    terms.add(token)
    return {term for term in terms if term and term not in _GENERIC_TERMS}


def extract_subject_terms(text: str) -> set[str]:
    """Return likely entity/project tokens that should anchor evidence."""
    normalized = normalize_text(text)
    subject_terms: set[str] = {
        word
        for word in _WORD_RE.findall(normalized)
        if len(word) >= 3 and word not in _GENERIC_TERMS
    }
    for match in re.finditer(
        r"([\u4e00-\u9fff]{2,12})(?=(项目|负责人|发布时间|预算|供应商|合同|阶段|状态|决策|风险|待办))",
        normalized,
    ):
        candidate = match.group(1).rstrip("的")
        if candidate not in _GENERIC_TERMS and candidate not in _ATTRIBUTE_TERMS:
            subject_terms.add(candidate)
    return subject_terms


def iter_text_lines(text: str) -> list[str]:
    """Split text into short, readable extractive units."""
    lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip(" -\t")
        if not line:
            continue
        parts = re.split(r"(?<=[。！？!?；;])\s*", line)
        for part in parts:
            cleaned = part.strip()
            if cleaned:
                lines.append(cleaned)
    return lines


def canonicalize_fact_key(raw_key: str) -> FactKey | None:
    normalized = normalize_text(raw_key).replace(" ", "")
    for fact_key, aliases in _FACT_KEY_ALIASES:
        for alias in aliases:
            alias_normalized = normalize_text(alias).replace(" ", "")
            if alias_normalized and alias_normalized in normalized:
                return fact_key
    return None


def extract_requested_fact_keys(question: str) -> tuple[FactKey, ...]:
    normalized = normalize_text(question).replace(" ", "")
    requested: list[FactKey] = []
    for fact_key, aliases in _FACT_KEY_ALIASES:
        for alias in aliases:
            alias_normalized = normalize_text(alias).replace(" ", "")
            if alias_normalized and alias_normalized in normalized:
                requested.append(fact_key)
                break
    return tuple(dict.fromkeys(requested))


def extract_requested_insight_kinds(question: str) -> tuple[InsightKind, ...]:
    requested_fact_keys = extract_requested_fact_keys(question)
    insight_kinds = [
        fact_key for fact_key in requested_fact_keys if fact_key in {"decision", "risk", "todo"}
    ]
    return tuple(insight_kinds)


def is_compare_request(question: str) -> bool:
    normalized = normalize_text(question)
    return any(token in normalized for token in _COMPARE_REQUEST_TERMS)


def is_timeline_request(question: str) -> bool:
    normalized = normalize_text(question)
    return any(token in normalized for token in _TIMELINE_REQUEST_TERMS)


def is_summary_request(question: str) -> bool:
    normalized = normalize_text(question)
    return any(token in normalized for token in _SUMMARY_REQUEST_TERMS)


def is_enumeration_request(question: str) -> bool:
    normalized = normalize_text(question)
    return any(token in normalized for token in _ENUMERATION_REQUEST_TERMS)


@dataclass(frozen=True)
class FactRecord:
    key: FactKey
    raw_key: str
    value: str
    normalized_value: str
    line_text: str


@dataclass(frozen=True)
class EvidenceUnit:
    text: str
    normalized_text: str
    facts: tuple[FactRecord, ...] = ()
    insight_kinds: tuple[InsightKind, ...] = ()


def parse_fact_line(line: str) -> FactRecord | None:
    match = _FACT_LINE_RE.match(line.strip())
    if match is None:
        return None
    raw_key = match.group("key").strip()
    value = match.group("value").strip()
    if not raw_key or not value:
        return None
    fact_key = canonicalize_fact_key(raw_key)
    if fact_key is None:
        return None
    return FactRecord(
        key=fact_key,
        raw_key=raw_key,
        value=value,
        normalized_value=normalize_fact_value(value),
        line_text=line.strip(),
    )


def extract_fact_records(text: str) -> tuple[FactRecord, ...]:
    records: list[FactRecord] = []
    seen: set[tuple[FactKey, str, str]] = set()
    for line in iter_text_lines(text):
        for record in _extract_fact_records_from_line(line):
            dedupe_key = (record.key, record.normalized_value, record.line_text.casefold())
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            records.append(record)
    return tuple(records)


def extract_evidence_units(text: str) -> tuple[EvidenceUnit, ...]:
    units: list[EvidenceUnit] = []
    for line in iter_text_lines(text):
        normalized_text = normalize_text(line)
        units.append(
            EvidenceUnit(
                text=line,
                normalized_text=normalized_text,
                facts=_extract_fact_records_from_line(line),
                insight_kinds=extract_insight_kinds(line),
            )
        )
    return tuple(units)


def extract_insight_kinds(text: str) -> tuple[InsightKind, ...]:
    normalized = text.casefold().strip()
    matched: list[InsightKind] = []
    for kind, prefixes in _INSIGHT_PREFIXES.items():
        if any(normalized.startswith(prefix) for prefix in prefixes):
            matched.append(kind)
            continue
        if any(pattern.search(text) for pattern in _INSIGHT_PATTERNS[kind]):
            matched.append(kind)
    return tuple(dict.fromkeys(matched))


def clean_insight_text(text: str) -> str:
    stripped = text.strip()
    lowered = stripped.casefold()
    for prefixes in _INSIGHT_PREFIXES.values():
        for prefix in prefixes:
            if lowered.startswith(prefix):
                candidate = stripped[len(prefix) :].strip()
                if candidate:
                    return candidate
    return stripped


def fact_aliases(fact_key: FactKey) -> tuple[str, ...]:
    return _ATTRIBUTE_ALIAS_INDEX[fact_key]


def sentence_matches_requested_fact(text: str, requested_fact_keys: set[FactKey]) -> bool:
    normalized = normalize_text(text).replace(" ", "")
    return any(
        normalize_text(alias).replace(" ", "") in normalized
        for fact_key in requested_fact_keys
        for alias in fact_aliases(fact_key)
    )


def _extract_fact_records_from_line(line: str) -> tuple[FactRecord, ...]:
    direct_record = parse_fact_line(line)
    if direct_record is not None:
        # Structured key/value lines own their semantic meaning. Re-parsing them
        # with free-text rules creates duplicate or cross-key facts from the same line.
        return (direct_record,)

    records: list[FactRecord] = []
    seen: set[tuple[FactKey, str, str]] = set()
    stripped = line.strip()
    for fact_key, raw_key, pattern in _NATURAL_FACT_PATTERNS:
        match = pattern.search(stripped)
        if match is None:
            continue
        value = match.group("value").strip().strip("。；;，,")
        if not value:
            continue
        record = FactRecord(
            key=fact_key,
            raw_key=raw_key,
            value=value,
            normalized_value=normalize_fact_value(value),
            line_text=stripped,
        )
        dedupe_key = (record.key, record.normalized_value, record.line_text.casefold())
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        records.append(record)
    return tuple(records)


def dedupe_citations(citations: list[Citation]) -> list[Citation]:
    seen: set[tuple[str, str]] = set()
    unique: list[Citation] = []
    for citation in citations:
        key = (citation.doc_id, citation.chunk_id)
        if key in seen:
            continue
        seen.add(key)
        unique.append(citation)
    return unique


def format_source_label(title: str, path: str) -> str:
    return f"{title}（{path}）"


@dataclass(frozen=True)
class QueryPlan:
    question: str
    intent: QueryIntent
    subject_terms: tuple[str, ...]
    requested_fact_keys: tuple[FactKey, ...]
    requested_insight_kinds: tuple[InsightKind, ...]


@dataclass(frozen=True)
class EvidenceItem:
    doc_id: str
    chunk_id: str
    title: str
    path: str
    score: float
    modified_at: datetime
    summary: str
    citation: Citation
    preview_text: str
    units: tuple[EvidenceUnit, ...] = ()
    facts: tuple[FactRecord, ...] = ()


def evidence_matches_subject(item: EvidenceItem, subject_terms: set[str]) -> bool:
    if not subject_terms:
        return True
    haystack = " ".join(
        [
            item.title,
            item.path,
            item.preview_text,
            *[unit.text for unit in item.units],
            *[fact.line_text for fact in item.facts],
        ]
    )
    return bool(subject_terms & extract_terms(haystack))


@dataclass(frozen=True)
class EvidenceBundle:
    query: str
    query_plan: QueryPlan
    trace_id: str
    items: list[EvidenceItem]
    total_candidates: int


@dataclass(frozen=True)
class ConflictSource:
    title: str
    path: str
    summary: str
    citation: Citation


@dataclass(frozen=True)
class QAResult:
    question: str
    trace_id: str
    result_type: QAResultType
    answer: str
    citations: list[Citation] = field(default_factory=list)
    checked_sources: list[str] = field(default_factory=list)
    suggested_next_steps: list[str] = field(default_factory=list)
    conflict_sources: list[ConflictSource] = field(default_factory=list)
    uncertainty_notes: list[str] = field(default_factory=list)
    memory_conflict_note: str | None = None


@dataclass(frozen=True)
class SummaryResult:
    trace_id: str
    result_type: Literal["summary"]
    summary: str
    citations: list[Citation] = field(default_factory=list)
    source_count: int = 0
    doc_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class InsightItem:
    kind: InsightKind
    text: str
    source_title: str
    source_path: str
    citations: list[Citation] = field(default_factory=list)


@dataclass(frozen=True)
class InsightResult:
    trace_id: str
    result_type: Literal["insights"]
    overview: str
    items: list[InsightItem] = field(default_factory=list)
    citations: list[Citation] = field(default_factory=list)
    source_count: int = 0
    doc_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ExportPreview:
    trace_id: str
    title: str
    markdown: str
    citations: list[Citation] = field(default_factory=list)


ResultPayload = QAResult | SummaryResult | InsightResult
