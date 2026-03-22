"""Prompt templates for QA pipeline — spec §12.3 Templates A/B/C."""

from __future__ import annotations

from opendocs.qa.models import EvidencePackage
from opendocs.retrieval.evidence import Citation

SYSTEM_PROMPT = (
    "你是 OpenDocs 文档助手。你只能根据提供的文档证据回答问题。\n"
    "规则：\n"
    "1. 每个事实性结论必须引用证据，使用 [CIT:chunk_id] 标记。\n"
    "2. 如果证据不足，明确说明。\n"
    "3. 不得编造不在证据中的事实。\n"
    "4. 用中文回答。"
)


def build_factual_prompt(package: EvidencePackage) -> str:
    """Template A: factual answer with citations."""
    parts = [f"问题：{package.query}\n\n证据：\n"]
    for r in package.results:
        text = package.chunk_texts.get(r.chunk_id, r.summary)
        parts.append(
            f"[EVIDENCE chunk_id={r.chunk_id}]\n"
            f"{text}\n"
            f"[/EVIDENCE]\n"
        )
    parts.append(
        "\n请根据以上证据回答问题。"
        "每个事实结论用 [CIT:chunk_id] 标注来源。"
    )
    return "".join(parts)


def build_conflict_prompt(
    package: EvidencePackage,
    conflict_groups: list[list[Citation]],
) -> str:
    """Template C: conflict display with multiple sources."""
    parts = [f"问题：{package.query}\n\n"]
    parts.append("以下证据存在冲突，请分别展示各方观点，不要归并为单一结论。\n\n")

    for i, group in enumerate(conflict_groups, 1):
        parts.append(f"冲突组 {i}：\n")
        for citation in group:
            text = package.chunk_texts.get(citation.chunk_id, citation.quote_preview)
            parts.append(
                f"[EVIDENCE chunk_id={citation.chunk_id}]\n"
                f"{text}\n"
                f"[/EVIDENCE]\n"
            )
        parts.append("\n")

    parts.append(
        "请列出冲突各方的观点，标注来源 [CIT:chunk_id]，"
        "并建议用户如何判断哪个版本更可信。"
    )
    return "".join(parts)


def build_insufficient_text(
    checked_sources: list[Citation],
) -> str:
    """Template B: evidence insufficient refusal (no LLM needed)."""
    parts = ["当前证据不足以可靠回答该问题。\n\n已检查来源：\n"]
    for i, src in enumerate(checked_sources[:5], 1):
        parts.append(f"{i}. {src.path}")
        if src.page_no is not None:
            parts.append(f" (第{src.page_no}页)")
        parts.append(f" — {src.quote_preview[:60]}\n")

    parts.append(
        "\n建议下一步：\n"
        "- 扩大检索范围或换用不同关键词\n"
        "- 指定具体时间范围、项目或目录\n"
        "- 检查是否有相关文档尚未纳入索引"
    )
    return "".join(parts)


NEXT_STEPS_INSUFFICIENT = [
    "扩大检索范围或换用不同关键词",
    "指定具体时间范围、项目或目录",
    "检查是否有相关文档尚未纳入索引",
]
