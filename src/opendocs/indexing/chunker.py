"""Heading/paragraph-aware document chunker."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from opendocs.parsers.base import ParsedDocument


def _estimate_tokens(text: str) -> int:
    """Rough token estimate with CJK / Latin differentiation.

    - CJK characters: ~1 token per 1.5 characters (≈ 0.67 token/char)
    - Latin / ASCII: ~1 token per 4 characters (≈ 0.25 token/char)
    - Whitespace (cp <= 0x20) is intentionally excluded: most tokenizers
      merge whitespace into adjacent tokens, so counting it separately
      would overestimate.  For whitespace-heavy content (code blocks,
      indented text) the estimate may be slightly low — acceptable for
      a heuristic used only for chunk size guidance.
    """
    cjk = 0
    latin = 0
    for ch in text:
        cp = ord(ch)
        if (0x4E00 <= cp <= 0x9FFF
                or 0x3400 <= cp <= 0x4DBF
                or 0xF900 <= cp <= 0xFAFF
                or 0x20000 <= cp <= 0x2FA1F):
            cjk += 1
        elif cp > 0x20:
            latin += 1
    return max(1, int(cjk / 1.5) + int(latin / 4))


def _detect_cjk_ratio(text: str) -> float:
    """Return ratio of CJK characters in *text* (0.0–1.0)."""
    if not text:
        return 0.0
    cjk = 0
    total = 0
    for ch in text:
        cp = ord(ch)
        if cp <= 0x20:
            continue
        total += 1
        if (0x4E00 <= cp <= 0x9FFF
                or 0x3400 <= cp <= 0x4DBF
                or 0xF900 <= cp <= 0xFAFF
                or 0x20000 <= cp <= 0x2FA1F):
            cjk += 1
    return cjk / total if total else 0.0


class ChunkConfig(BaseModel):
    """Configuration for the chunker.

    ``max_chars`` defaults to 900 which suits CJK-dominant text (spec §8.3:
    600–1200 chars).  For Latin-dominant text the chunker automatically
    raises the effective limit to ``max_chars_latin`` (default 2400, ≈ 600
    tokens at 4 chars/token) so that English chunks fall within the spec
    target of 350–700 tokens.
    """

    max_chars: int = Field(default=900, ge=50)
    max_chars_latin: int = Field(default=2400, ge=50)
    overlap_ratio: float = Field(default=0.12, ge=0.0, le=0.5)
    min_chunk_chars: int = Field(default=50, ge=1)


@dataclass
class ChunkResult:
    """A single chunk produced from a parsed document.

    When overlap is enabled, ``text`` may contain a prefix carried over from
    the previous chunk.  ``char_start`` and ``char_end`` always refer to the
    *new* content's position in the source document (i.e. they correspond to
    the paragraph offsets, not to the overlap prefix).  This means
    ``len(text) >= char_end - char_start`` when overlap is present.
    """

    chunk_index: int
    text: str
    char_start: int
    char_end: int
    page_no: int | None
    paragraph_start: int
    paragraph_end: int
    heading_path: str | None
    token_estimate: int
    chunk_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    doc_id: str | None = None
    embedding_model: str | None = None
    embedding_key: str | None = None


class Chunker:
    """Split a ``ParsedDocument`` into ``ChunkResult`` items.

    Strategy (by priority):
    1. Very short document → single chunk
    2. Heading boundary: force split when heading_path changes
    3. Paragraph boundary: accumulate until near max_chars
    4. Intra-paragraph split: when a single paragraph > max_chars
    5. Overlap: each new chunk starts with tail of previous chunk
    """

    def chunk(
        self,
        doc: ParsedDocument,
        config: ChunkConfig | None = None,
        doc_id: str | None = None,
    ) -> list[ChunkResult]:
        cfg = config or ChunkConfig()

        # Pick effective max_chars based on document language (spec §8.3)
        cjk_ratio = _detect_cjk_ratio(doc.raw_text)
        effective_max = cfg.max_chars if cjk_ratio >= 0.3 else cfg.max_chars_latin

        # Reject failed documents explicitly
        if doc.parse_status == "failed":
            return []

        # No paragraphs or tiny doc → single chunk
        if not doc.paragraphs:
            if not doc.raw_text.strip():
                return []
            return [
                ChunkResult(
                    chunk_index=0,
                    text=doc.raw_text,
                    char_start=0,
                    char_end=len(doc.raw_text),
                    page_no=None,
                    paragraph_start=0,
                    paragraph_end=0,
                    heading_path=None,
                    token_estimate=_estimate_tokens(doc.raw_text),
                    doc_id=doc_id,
                )
            ]

        if len(doc.raw_text) < cfg.min_chunk_chars:
            p = doc.paragraphs
            return [
                ChunkResult(
                    chunk_index=0,
                    text=doc.raw_text,
                    char_start=0,
                    char_end=len(doc.raw_text),
                    page_no=p[0].page_no if p else None,
                    paragraph_start=p[0].index if p else 0,
                    paragraph_end=p[-1].index if p else 0,
                    heading_path=p[0].heading_path if p else None,
                    token_estimate=_estimate_tokens(doc.raw_text),
                    doc_id=doc_id,
                )
            ]

        # Group paragraphs into segments by locator boundary.
        # Heading changes must split chunks, and PDF page changes must also
        # split chunks so that page_no remains truthful for citations.
        segments: list[list[int]] = []  # list of paragraph indices
        sentinel = object()
        current_segment_key: object | tuple[str | None, int | None] = sentinel
        for i, para in enumerate(doc.paragraphs):
            segment_key = (para.heading_path, para.page_no)
            if segment_key != current_segment_key:
                segments.append([])
                current_segment_key = segment_key
            segments[-1].append(i)

        overlap_chars = int(effective_max * cfg.overlap_ratio)
        results: list[ChunkResult] = []
        chunk_idx = 0
        prev_tail = ""  # overlap text from previous chunk

        for seg in segments:
            # Reset overlap at heading boundaries – overlap must not carry
            # text from a different heading section into a new one, as this
            # would create semantically confusing chunks (ADR-0010 scope).
            prev_tail = ""

            # Within a segment, accumulate paragraphs until effective_max
            buf_paras: list[int] = []
            buf_len = 0

            for pi in seg:
                para = doc.paragraphs[pi]
                para_len = len(para.text)

                # Would adding this paragraph exceed effective_max?
                projected = buf_len + (1 if buf_len > 0 else 0) + para_len
                overlap_extra = len(prev_tail) + 1 if prev_tail and not buf_paras else 0
                total = projected + overlap_extra

                if buf_paras and total > effective_max:
                    # Flush current buffer
                    chunk_idx = self._flush_buf(
                        doc, buf_paras, results, chunk_idx, prev_tail, cfg,
                        doc_id=doc_id,
                    )
                    # Prepare overlap from just-flushed chunk
                    prev_tail = self._get_tail(results[-1].text, overlap_chars)
                    buf_paras = []
                    buf_len = 0

                # Handle single paragraph exceeding effective_max
                if para_len > effective_max:
                    # Flush any accumulated
                    if buf_paras:
                        chunk_idx = self._flush_buf(
                            doc, buf_paras, results, chunk_idx, prev_tail, cfg,
                            doc_id=doc_id,
                        )
                        prev_tail = self._get_tail(results[-1].text, overlap_chars)
                        buf_paras = []
                        buf_len = 0

                    # Split long paragraph into sub-chunks
                    chunk_idx, prev_tail = self._split_long_para(
                        doc, pi, results, chunk_idx, prev_tail,
                        effective_max, overlap_chars,
                        doc_id=doc_id,
                    )
                    continue

                buf_paras.append(pi)
                buf_len += (1 if buf_len > 0 else 0) + para_len

            # Flush remaining in segment
            if buf_paras:
                chunk_idx = self._flush_buf(
                    doc, buf_paras, results, chunk_idx, prev_tail, cfg,
                    doc_id=doc_id,
                )
                prev_tail = self._get_tail(results[-1].text, overlap_chars)

        return results

    # ------------------------------------------------------------------

    @staticmethod
    def _flush_buf(
        doc: ParsedDocument,
        para_indices: list[int],
        results: list[ChunkResult],
        chunk_idx: int,
        prev_tail: str,
        cfg: ChunkConfig,
        doc_id: str | None = None,
    ) -> int:
        paras = [doc.paragraphs[i] for i in para_indices]
        body = "\n".join(p.text for p in paras)
        if prev_tail:
            text = prev_tail + "\n" + body
        else:
            text = body

        first = paras[0]
        last = paras[-1]
        results.append(
            ChunkResult(
                chunk_index=chunk_idx,
                text=text,
                char_start=first.start_char,
                char_end=last.end_char,
                page_no=first.page_no,
                paragraph_start=first.index,
                paragraph_end=last.index,
                heading_path=first.heading_path,
                token_estimate=_estimate_tokens(text),
                doc_id=doc_id,
            )
        )
        return chunk_idx + 1

    @staticmethod
    def _find_break_point(text: str, hard_end: int, search_back: int = 80) -> int:
        """Find a natural break point near *hard_end*, searching back up to *search_back* chars.

        Prefers (in order): newline, Chinese period, period+space, semicolon, comma, space.
        Falls back to *hard_end* if nothing found.
        """
        if hard_end >= len(text):
            return hard_end

        search_start = max(0, hard_end - search_back)
        window = text[search_start:hard_end]

        # Priority ordered break characters
        for sep in ("\n", "。", "！", "？", ".\u0020", "；", ";", "，", ",", " "):
            idx = window.rfind(sep)
            if idx != -1:
                return search_start + idx + len(sep)

        return hard_end

    @staticmethod
    def _split_long_para(
        doc: ParsedDocument,
        para_idx: int,
        results: list[ChunkResult],
        chunk_idx: int,
        prev_tail: str,
        effective_max: int,
        overlap_chars: int,
        doc_id: str | None = None,
    ) -> tuple[int, str]:
        para = doc.paragraphs[para_idx]
        text = para.text
        pos = 0

        while pos < len(text):
            budget = effective_max
            if prev_tail:
                budget -= len(prev_tail) + 1

            hard_end = min(pos + budget, len(text))
            # Try to break at a natural sentence/clause boundary
            end = Chunker._find_break_point(text, hard_end)
            # Prevent zero-progress if break point lands at or before pos
            if end <= pos:
                end = hard_end

            chunk_text = text[pos:end]
            if prev_tail:
                chunk_text = prev_tail + "\n" + chunk_text

            results.append(
                ChunkResult(
                    chunk_index=chunk_idx,
                    text=chunk_text,
                    char_start=para.start_char + pos,
                    char_end=para.start_char + end,
                    page_no=para.page_no,
                    paragraph_start=para.index,
                    paragraph_end=para.index,
                    heading_path=para.heading_path,
                    token_estimate=_estimate_tokens(chunk_text),
                    doc_id=doc_id,
                )
            )
            chunk_idx += 1
            prev_tail = text[max(0, end - overlap_chars) : end]
            pos = end

        return chunk_idx, prev_tail

    @staticmethod
    def _get_tail(text: str, n: int) -> str:
        if n <= 0:
            return ""
        return text[-n:]
