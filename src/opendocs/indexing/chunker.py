"""Heading/paragraph-aware document chunker."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel

from opendocs.parsers.base import ParsedDocument


class ChunkConfig(BaseModel):
    """Configuration for the chunker."""

    max_chars: int = 900
    overlap_ratio: float = 0.12
    min_chunk_chars: int = 50


@dataclass
class ChunkResult:
    """A single chunk produced from a parsed document."""

    chunk_index: int
    text: str
    char_start: int
    char_end: int
    page_no: int | None
    paragraph_start: int
    paragraph_end: int
    heading_path: str | None
    token_estimate: int


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
    ) -> list[ChunkResult]:
        cfg = config or ChunkConfig()

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
                    token_estimate=len(doc.raw_text),
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
                    token_estimate=len(doc.raw_text),
                )
            ]

        # Group paragraphs into segments by heading_path
        # Each segment: list of consecutive paragraphs with same heading_path
        segments: list[list[int]] = []  # list of paragraph indices
        current_heading: str | None = object()  # sentinel
        for i, para in enumerate(doc.paragraphs):
            if para.heading_path != current_heading:
                segments.append([])
                current_heading = para.heading_path
            segments[-1].append(i)

        overlap_chars = int(cfg.max_chars * cfg.overlap_ratio)
        results: list[ChunkResult] = []
        chunk_idx = 0
        prev_tail = ""  # overlap text from previous chunk

        for seg in segments:
            # Within a segment, accumulate paragraphs until max_chars
            buf_paras: list[int] = []
            buf_len = 0

            for pi in seg:
                para = doc.paragraphs[pi]
                para_len = len(para.text)

                # Would adding this paragraph exceed max_chars?
                projected = buf_len + (1 if buf_len > 0 else 0) + para_len
                overlap_extra = len(prev_tail) + 1 if prev_tail and not buf_paras else 0
                total = projected + overlap_extra

                if buf_paras and total > cfg.max_chars:
                    # Flush current buffer
                    chunk_idx = self._flush_buf(
                        doc, buf_paras, results, chunk_idx, prev_tail, cfg,
                    )
                    # Prepare overlap from just-flushed chunk
                    prev_tail = self._get_tail(results[-1].text, overlap_chars)
                    buf_paras = []
                    buf_len = 0

                # Handle single paragraph exceeding max_chars
                if para_len > cfg.max_chars:
                    # Flush any accumulated
                    if buf_paras:
                        chunk_idx = self._flush_buf(
                            doc, buf_paras, results, chunk_idx, prev_tail, cfg,
                        )
                        prev_tail = self._get_tail(results[-1].text, overlap_chars)
                        buf_paras = []
                        buf_len = 0

                    # Split long paragraph into sub-chunks
                    chunk_idx, prev_tail = self._split_long_para(
                        doc, pi, results, chunk_idx, prev_tail, cfg, overlap_chars,
                    )
                    continue

                buf_paras.append(pi)
                buf_len += (1 if buf_len > 0 else 0) + para_len

            # Flush remaining in segment
            if buf_paras:
                chunk_idx = self._flush_buf(
                    doc, buf_paras, results, chunk_idx, prev_tail, cfg,
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
                token_estimate=len(text),
            )
        )
        return chunk_idx + 1

    @staticmethod
    def _split_long_para(
        doc: ParsedDocument,
        para_idx: int,
        results: list[ChunkResult],
        chunk_idx: int,
        prev_tail: str,
        cfg: ChunkConfig,
        overlap_chars: int,
    ) -> tuple[int, str]:
        para = doc.paragraphs[para_idx]
        text = para.text
        pos = 0

        while pos < len(text):
            budget = cfg.max_chars
            if prev_tail:
                budget -= len(prev_tail) + 1

            end = min(pos + budget, len(text))
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
                    token_estimate=len(chunk_text),
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
