"""Tests for the Chunker."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from opendocs.indexing.chunker import ChunkConfig, Chunker
from opendocs.parsers.base import Paragraph, ParsedDocument


def _make_doc(
    paragraphs: list[Paragraph],
    raw_text: str = "",
    file_type: str = "txt",
) -> ParsedDocument:
    if not raw_text and paragraphs:
        raw_text = "\n".join(p.text for p in paragraphs)
    return ParsedDocument(
        file_path="test.txt",
        file_type=file_type,
        raw_text=raw_text,
        paragraphs=paragraphs,
    )


class TestChunkConfigValidation:
    def test_default_values(self) -> None:
        cfg = ChunkConfig()
        assert cfg.max_chars == 900
        assert cfg.overlap_ratio == 0.12
        assert cfg.min_chunk_chars == 50

    def test_overlap_ratio_too_high(self) -> None:
        with pytest.raises(ValidationError):
            ChunkConfig(overlap_ratio=0.8)

    def test_overlap_ratio_negative(self) -> None:
        with pytest.raises(ValidationError):
            ChunkConfig(overlap_ratio=-0.1)

    def test_max_chars_too_small(self) -> None:
        with pytest.raises(ValidationError):
            ChunkConfig(max_chars=10)

    def test_min_chunk_chars_zero(self) -> None:
        with pytest.raises(ValidationError):
            ChunkConfig(min_chunk_chars=0)


class TestChunkerShortDoc:
    def test_empty_doc(self) -> None:
        doc = _make_doc([], raw_text="")
        chunks = Chunker().chunk(doc)
        assert chunks == []

    def test_chunk_failed_document(self) -> None:
        """S2-T04: a failed ParsedDocument must produce zero chunks."""
        doc = ParsedDocument(
            file_path="bad.txt",
            file_type="txt",
            raw_text="",
            parse_status="failed",
            error_info="corruption",
        )
        assert Chunker().chunk(doc) == []

    def test_chunk_failed_document_with_nonempty_raw(self) -> None:
        """Failed doc with non-empty raw_text must still produce zero chunks."""
        doc = ParsedDocument(
            file_path="bad.txt",
            file_type="txt",
            raw_text="some leftover text",
            parse_status="failed",
            error_info="bad status",
        )
        assert Chunker().chunk(doc) == []

    def test_very_short_doc(self) -> None:
        doc = _make_doc(
            [Paragraph(text="Hi", index=0, start_char=0, end_char=2)],
            raw_text="Hi",
        )
        config = ChunkConfig(min_chunk_chars=50)
        chunks = Chunker().chunk(doc, config)
        assert len(chunks) == 1
        assert chunks[0].text == "Hi"
        assert chunks[0].chunk_index == 0

    def test_no_paragraphs_with_text(self) -> None:
        doc = _make_doc([], raw_text="Some text")
        chunks = Chunker().chunk(doc)
        assert len(chunks) == 1
        assert chunks[0].text == "Some text"


class TestChunkerParagraphBoundary:
    def test_multiple_paragraphs(self) -> None:
        paras = [
            Paragraph(text="A" * 400, index=0, start_char=0, end_char=400),
            Paragraph(text="B" * 400, index=1, start_char=401, end_char=801),
            Paragraph(text="C" * 400, index=2, start_char=802, end_char=1202),
        ]
        doc = _make_doc(paras)
        # Pin max_chars_latin = max_chars so language detection doesn't change limit
        config = ChunkConfig(
            max_chars=900, max_chars_latin=900, overlap_ratio=0.0, min_chunk_chars=50
        )
        chunks = Chunker().chunk(doc, config)

        # Two paragraphs of 400+1+400=801 fit in 900, third doesn't
        assert len(chunks) >= 2
        assert chunks[0].paragraph_start == 0
        assert chunks[0].paragraph_end <= 1

    def test_paragraph_start_end(self) -> None:
        paras = [
            Paragraph(text="Para 0", index=0, start_char=0, end_char=6),
            Paragraph(text="Para 1", index=1, start_char=7, end_char=13),
        ]
        doc = _make_doc(paras)
        config = ChunkConfig(max_chars=5000, overlap_ratio=0.0, min_chunk_chars=5)
        chunks = Chunker().chunk(doc, config)
        assert len(chunks) == 1
        assert chunks[0].paragraph_start == 0
        assert chunks[0].paragraph_end == 1


class TestChunkerHeadingBoundary:
    def test_heading_change_forces_split(self) -> None:
        paras = [
            Paragraph(
                text="A" * 100,
                index=0,
                start_char=0,
                end_char=100,
                heading_path="Intro",
            ),
            Paragraph(
                text="B" * 100,
                index=1,
                start_char=101,
                end_char=201,
                heading_path="Chapter 1",
            ),
        ]
        doc = _make_doc(paras)
        config = ChunkConfig(max_chars=5000, overlap_ratio=0.0, min_chunk_chars=5)
        chunks = Chunker().chunk(doc, config)

        # Different heading_path → forced split
        assert len(chunks) == 2
        assert chunks[0].heading_path == "Intro"
        assert chunks[1].heading_path == "Chapter 1"


class TestChunkerPageBoundary:
    def test_page_change_forces_split_even_when_heading_matches(self) -> None:
        paras = [
            Paragraph(
                text="Page one content",
                index=0,
                start_char=0,
                end_char=16,
                page_no=1,
                heading_path="Methods",
            ),
            Paragraph(
                text="Page two content",
                index=1,
                start_char=17,
                end_char=33,
                page_no=2,
                heading_path="Methods",
            ),
        ]
        doc = _make_doc(paras)
        config = ChunkConfig(
            max_chars=5000,
            max_chars_latin=5000,
            overlap_ratio=0.0,
            min_chunk_chars=5,
        )

        chunks = Chunker().chunk(doc, config)

        assert len(chunks) == 2
        assert chunks[0].page_no == 1
        assert chunks[0].paragraph_start == 0
        assert chunks[0].paragraph_end == 0
        assert chunks[1].page_no == 2
        assert chunks[1].paragraph_start == 1
        assert chunks[1].paragraph_end == 1


class TestChunkerHeadingOverlapReset:
    """Overlap must NOT cross heading boundaries (semantic isolation)."""

    def test_no_overlap_across_heading_boundary(self) -> None:
        """When heading_path changes, the new segment's first chunk must NOT
        start with tail text from the previous segment."""
        paras = [
            Paragraph(
                text="A" * 500,
                index=0,
                start_char=0,
                end_char=500,
                heading_path="Intro",
            ),
            Paragraph(
                text="B" * 500,
                index=1,
                start_char=501,
                end_char=1001,
                heading_path="Chapter 1",
            ),
        ]
        doc = _make_doc(paras)
        config = ChunkConfig(
            max_chars=600,
            max_chars_latin=600,
            overlap_ratio=0.12,
            min_chunk_chars=5,
        )
        chunks = Chunker().chunk(doc, config)
        assert len(chunks) == 2
        # Second chunk (Chapter 1) must NOT contain any 'A' from Intro
        assert "A" not in chunks[1].text, "Overlap leaked across heading boundary"
        # First chunk must be pure A's
        assert set(chunks[0].text) == {"A"}


class TestChunkerLongParagraph:
    def test_long_paragraph_split(self) -> None:
        long_text = "X" * 2000
        paras = [
            Paragraph(text=long_text, index=0, start_char=0, end_char=2000),
        ]
        doc = _make_doc(paras, raw_text=long_text)
        config = ChunkConfig(
            max_chars=900, max_chars_latin=900, overlap_ratio=0.0, min_chunk_chars=50
        )
        chunks = Chunker().chunk(doc, config)

        assert len(chunks) >= 3  # 2000 / 900 ≈ 3
        for c in chunks:
            assert c.paragraph_start == 0
            assert c.paragraph_end == 0


class TestChunkerNaturalBreak:
    def test_splits_at_chinese_period(self) -> None:
        """Long paragraph should break at '。' rather than mid-sentence."""
        # Build text: 50 Chinese sentences of ~18 chars each = ~900 chars total
        sentence = "这是一个测试句子内容。"  # 10 chars
        long_text = sentence * 100  # 1000 chars
        paras = [
            Paragraph(text=long_text, index=0, start_char=0, end_char=len(long_text)),
        ]
        doc = _make_doc(paras, raw_text=long_text)
        config = ChunkConfig(
            max_chars=900, max_chars_latin=900, overlap_ratio=0.0, min_chunk_chars=50
        )
        chunks = Chunker().chunk(doc, config)
        assert len(chunks) >= 2
        # First chunk should end at a sentence boundary (after '。')
        assert chunks[0].text.endswith("。")

    def test_splits_at_english_period(self) -> None:
        """Long English paragraph should break at '. ' rather than mid-word."""
        sentence = "This is a test sentence. "
        long_text = sentence * 50  # ~1250 chars
        paras = [
            Paragraph(
                text=long_text.strip(), index=0, start_char=0, end_char=len(long_text.strip())
            ),
        ]
        doc = _make_doc(paras, raw_text=long_text.strip())
        config = ChunkConfig(
            max_chars=500, max_chars_latin=500, overlap_ratio=0.0, min_chunk_chars=50
        )
        chunks = Chunker().chunk(doc, config)
        assert len(chunks) >= 2
        # First chunk should end at a sentence boundary
        assert chunks[0].text.rstrip().endswith(".")

    def test_hard_cut_when_no_break_point(self) -> None:
        """If no natural break point exists, still makes progress."""
        # A single long string with no sentence boundaries
        long_text = "X" * 2000
        paras = [
            Paragraph(text=long_text, index=0, start_char=0, end_char=2000),
        ]
        doc = _make_doc(paras, raw_text=long_text)
        config = ChunkConfig(
            max_chars=900, max_chars_latin=900, overlap_ratio=0.0, min_chunk_chars=50
        )
        chunks = Chunker().chunk(doc, config)
        assert len(chunks) >= 3
        # All text should be covered
        total = sum(c.char_end - c.char_start for c in chunks)
        assert total == 2000


class TestChunkerLanguageAware:
    def test_english_uses_larger_max(self) -> None:
        """English-dominant text should use max_chars_latin (larger chunks)."""
        # 2000 chars of English text – with default max_chars=900 (CJK)
        # this would split into 3+ chunks, but max_chars_latin=2400 should
        # keep it in 1 chunk.
        eng = "word " * 400  # 2000 chars
        paras = [
            Paragraph(text=eng.strip(), index=0, start_char=0, end_char=len(eng.strip())),
        ]
        doc = _make_doc(paras, raw_text=eng.strip())
        config = ChunkConfig(
            max_chars=900,
            max_chars_latin=2400,
            overlap_ratio=0.0,
            min_chunk_chars=50,
        )
        chunks = Chunker().chunk(doc, config)
        assert len(chunks) == 1

    def test_chinese_uses_smaller_max(self) -> None:
        """Chinese-dominant text should use max_chars (smaller chunks)."""
        cn = "中" * 2000
        paras = [
            Paragraph(text=cn, index=0, start_char=0, end_char=2000),
        ]
        doc = _make_doc(paras, raw_text=cn)
        config = ChunkConfig(
            max_chars=900,
            max_chars_latin=2400,
            overlap_ratio=0.0,
            min_chunk_chars=50,
        )
        chunks = Chunker().chunk(doc, config)
        # 2000 / 900 → at least 3 chunks
        assert len(chunks) >= 3

    def test_config_max_chars_latin_validation(self) -> None:
        with pytest.raises(ValidationError):
            ChunkConfig(max_chars_latin=10)


class TestChunkerOverlap:
    def test_overlap_present(self) -> None:
        paras = [
            Paragraph(text="A" * 500, index=0, start_char=0, end_char=500),
            Paragraph(text="B" * 500, index=1, start_char=501, end_char=1001),
        ]
        doc = _make_doc(paras)
        config = ChunkConfig(
            max_chars=600, max_chars_latin=600, overlap_ratio=0.12, min_chunk_chars=50
        )
        chunks = Chunker().chunk(doc, config)

        assert len(chunks) >= 2
        # Second chunk should start with overlap from first
        if len(chunks) >= 2:
            # The overlap text from end of first chunk should appear at start of second
            overlap_len = int(600 * 0.12)
            tail_of_first = chunks[0].text[-overlap_len:]
            assert chunks[1].text.startswith(tail_of_first)

    def test_overlap_ratio_within_spec_range(self) -> None:
        """Overlap ratio must be between 10% and 15% per spec section 8.3."""
        # Build a multi-chunk document so overlap actually occurs
        sentence = "这是一段测试内容。"  # 9 chars
        long_text = sentence * 200  # 1800 chars → multiple chunks at max_chars=900
        paras = [
            Paragraph(text=long_text, index=0, start_char=0, end_char=len(long_text)),
        ]
        doc = _make_doc(paras, raw_text=long_text)

        for ratio in (0.10, 0.12, 0.15):
            config = ChunkConfig(
                max_chars=900,
                max_chars_latin=900,
                overlap_ratio=ratio,
                min_chunk_chars=50,
            )
            chunks = Chunker().chunk(doc, config)
            assert len(chunks) >= 2, f"Expected multiple chunks at ratio={ratio}"
            for i in range(1, len(chunks)):
                prev_text = chunks[i - 1].text
                cur_text = chunks[i].text
                # Simpler check: overlap chars = len(prev_tail) used
                overlap_chars = int(config.max_chars * ratio)
                expected_tail = prev_text[-overlap_chars:]
                assert cur_text.startswith(expected_tail), (
                    f"ratio={ratio}, chunk {i}: expected overlap prefix not found"
                )


class TestChunkerMetadata:
    def test_char_start_end(self) -> None:
        paras = [
            Paragraph(text="Hello", index=0, start_char=0, end_char=5),
            Paragraph(text="World", index=1, start_char=6, end_char=11),
        ]
        doc = _make_doc(paras)
        config = ChunkConfig(max_chars=5000, overlap_ratio=0.0, min_chunk_chars=5)
        chunks = Chunker().chunk(doc, config)
        assert chunks[0].char_start == 0
        assert chunks[0].char_end == 11

    def test_page_no_preserved(self) -> None:
        paras = [
            Paragraph(text="Page1", index=0, start_char=0, end_char=5, page_no=1),
            Paragraph(text="Page2", index=1, start_char=6, end_char=11, page_no=2),
        ]
        doc = _make_doc(paras)
        config = ChunkConfig(max_chars=5000, overlap_ratio=0.0, min_chunk_chars=5)
        chunks = Chunker().chunk(doc, config)
        # Single chunk, page_no = first paragraph's page
        assert chunks[0].page_no == 1

    def test_heading_path_preserved(self) -> None:
        paras = [
            Paragraph(
                text="Content",
                index=0,
                start_char=0,
                end_char=7,
                heading_path="A > B",
            ),
        ]
        doc = _make_doc(paras)
        chunks = Chunker().chunk(doc)
        assert chunks[0].heading_path == "A > B"

    def test_token_estimate(self) -> None:
        paras = [
            Paragraph(text="Hello World", index=0, start_char=0, end_char=11),
        ]
        doc = _make_doc(paras)
        chunks = Chunker().chunk(doc)
        # token_estimate should be a positive integer
        assert chunks[0].token_estimate >= 1

    def test_token_estimate_chinese(self) -> None:
        """Chinese text should produce reasonable token estimates."""
        chinese = "这是一段中文测试文本。"
        paras = [
            Paragraph(text=chinese, index=0, start_char=0, end_char=len(chinese)),
        ]
        doc = _make_doc(paras)
        chunks = Chunker().chunk(doc)
        # CJK: ~0.67 tokens per char → expect at least len/2
        assert chunks[0].token_estimate >= len(chinese) // 2

    def test_token_estimate_english_vs_chinese(self) -> None:
        """English text should produce fewer tokens per char than Chinese."""
        from opendocs.indexing.chunker import _estimate_tokens

        en = "Hello world this is a test sentence for token estimation."
        cn = "这是一段用来测试令牌估算的中文句子需要足够长才能比较。"
        en_ratio = _estimate_tokens(en) / len(en)
        cn_ratio = _estimate_tokens(cn) / len(cn)
        # CJK should have higher token density per character
        assert cn_ratio > en_ratio


class TestChunkerOffsetLocator:
    """char_start/char_end must locate valid content in raw_text."""

    def test_chunk_offsets_locate_in_raw_text(self) -> None:
        """For every chunk, raw_text[char_start:char_end] must be a substring of chunk.text."""
        paras = [
            Paragraph(text="A" * 500, index=0, start_char=0, end_char=500),
            Paragraph(text="B" * 500, index=1, start_char=501, end_char=1001),
            Paragraph(text="C" * 500, index=2, start_char=1002, end_char=1502),
        ]
        doc = _make_doc(paras)
        config = ChunkConfig(
            max_chars=600, max_chars_latin=600, overlap_ratio=0.12, min_chunk_chars=50
        )
        chunks = Chunker().chunk(doc, config)
        assert len(chunks) >= 2
        for c in chunks:
            located = doc.raw_text[c.char_start : c.char_end]
            assert located in c.text, (
                f"chunk {c.chunk_index}: raw_text[{c.char_start}:{c.char_end}] "
                f"not found in chunk text"
            )

    def test_chunk_offsets_cover_full_document(self) -> None:
        """Union of all chunk offset ranges must cover the entire raw_text."""
        text = "段落一的内容。" * 50 + "\n" + "段落二的内容。" * 50
        paras = [
            Paragraph(
                text="段落一的内容。" * 50,
                index=0,
                start_char=0,
                end_char=len("段落一的内容。" * 50),
            ),
            Paragraph(
                text="段落二的内容。" * 50,
                index=1,
                start_char=len("段落一的内容。" * 50) + 1,
                end_char=len(text),
            ),
        ]
        doc = _make_doc(paras, raw_text=text)
        config = ChunkConfig(
            max_chars=200, max_chars_latin=200, overlap_ratio=0.0, min_chunk_chars=50
        )
        chunks = Chunker().chunk(doc, config)
        # Every character in raw_text should be covered by at least one chunk's range
        covered = set()
        for c in chunks:
            covered.update(range(c.char_start, c.char_end))
        for i in range(len(doc.raw_text)):
            if doc.raw_text[i].strip():  # ignore whitespace-only gaps
                assert i in covered, f"char at position {i} not covered by any chunk"


class TestChunkerChineseBreakPoints:
    """Chunker should break at ！ and ？ in addition to 。"""

    def test_splits_at_chinese_exclamation(self) -> None:
        sentence = "这是一个测试内容！"  # 9 chars
        long_text = sentence * 120  # 1080 chars
        paras = [
            Paragraph(text=long_text, index=0, start_char=0, end_char=len(long_text)),
        ]
        doc = _make_doc(paras, raw_text=long_text)
        config = ChunkConfig(
            max_chars=900, max_chars_latin=900, overlap_ratio=0.0, min_chunk_chars=50
        )
        chunks = Chunker().chunk(doc, config)
        assert len(chunks) >= 2
        assert chunks[0].text.endswith("！")

    def test_splits_at_chinese_question(self) -> None:
        sentence = "这是一个测试问题？"  # 9 chars
        long_text = sentence * 120  # 1080 chars
        paras = [
            Paragraph(text=long_text, index=0, start_char=0, end_char=len(long_text)),
        ]
        doc = _make_doc(paras, raw_text=long_text)
        config = ChunkConfig(
            max_chars=900, max_chars_latin=900, overlap_ratio=0.0, min_chunk_chars=50
        )
        chunks = Chunker().chunk(doc, config)
        assert len(chunks) >= 2
        assert chunks[0].text.endswith("？")


class TestChunkerChunkId:
    """chunk_id must be auto-generated UUID for every chunk (spec §8.1.2)."""

    def test_chunk_id_auto_generated(self) -> None:
        import uuid

        paras = [
            Paragraph(text="Hello", index=0, start_char=0, end_char=5),
        ]
        doc = _make_doc(paras)
        chunks = Chunker().chunk(doc)
        assert len(chunks) == 1
        # Must be a valid UUID string
        parsed = uuid.UUID(chunks[0].chunk_id)
        assert str(parsed) == chunks[0].chunk_id

    def test_chunk_ids_unique(self) -> None:
        paras = [
            Paragraph(text="A" * 500, index=0, start_char=0, end_char=500),
            Paragraph(text="B" * 500, index=1, start_char=501, end_char=1001),
        ]
        doc = _make_doc(paras)
        config = ChunkConfig(
            max_chars=600, max_chars_latin=600, overlap_ratio=0.0, min_chunk_chars=50
        )
        chunks = Chunker().chunk(doc, config)
        assert len(chunks) >= 2
        ids = [c.chunk_id for c in chunks]
        assert len(set(ids)) == len(ids), "chunk_ids must be unique"


class TestChunkerDocId:
    """doc_id must propagate to all ChunkResult instances (spec §8.3)."""

    def test_doc_id_default_none(self) -> None:
        paras = [
            Paragraph(text="Hello", index=0, start_char=0, end_char=5),
        ]
        doc = _make_doc(paras)
        chunks = Chunker().chunk(doc)
        assert chunks[0].doc_id is None

    def test_doc_id_propagated(self) -> None:
        paras = [
            Paragraph(text="Hello", index=0, start_char=0, end_char=5),
        ]
        doc = _make_doc(paras)
        chunks = Chunker().chunk(doc, doc_id="abc-123")
        assert chunks[0].doc_id == "abc-123"

    def test_doc_id_on_multi_chunk(self) -> None:
        paras = [
            Paragraph(text="A" * 500, index=0, start_char=0, end_char=500),
            Paragraph(text="B" * 500, index=1, start_char=501, end_char=1001),
        ]
        doc = _make_doc(paras)
        config = ChunkConfig(
            max_chars=600, max_chars_latin=600, overlap_ratio=0.0, min_chunk_chars=50
        )
        chunks = Chunker().chunk(doc, config, doc_id="doc-42")
        assert len(chunks) >= 2
        for c in chunks:
            assert c.doc_id == "doc-42"

    def test_doc_id_on_long_para_split(self) -> None:
        long_text = "X" * 2000
        paras = [
            Paragraph(text=long_text, index=0, start_char=0, end_char=2000),
        ]
        doc = _make_doc(paras, raw_text=long_text)
        config = ChunkConfig(
            max_chars=900, max_chars_latin=900, overlap_ratio=0.0, min_chunk_chars=50
        )
        chunks = Chunker().chunk(doc, config, doc_id="split-id")
        assert len(chunks) >= 3
        for c in chunks:
            assert c.doc_id == "split-id"

    def test_doc_id_on_heading_split(self) -> None:
        paras = [
            Paragraph(text="A" * 100, index=0, start_char=0, end_char=100, heading_path="Intro"),
            Paragraph(text="B" * 100, index=1, start_char=101, end_char=201, heading_path="Ch1"),
        ]
        doc = _make_doc(paras)
        config = ChunkConfig(max_chars=5000, overlap_ratio=0.0, min_chunk_chars=5)
        chunks = Chunker().chunk(doc, config, doc_id="heading-doc")
        assert len(chunks) == 2
        for c in chunks:
            assert c.doc_id == "heading-doc"


class TestChunkerPartialDocument:
    """S2-T04: partial documents should be chunked like success (usable content)."""

    def test_partial_doc_produces_chunks(self) -> None:
        """A document with parse_status='partial' should still produce chunks
        from its available paragraphs."""
        paras = [
            Paragraph(text="Good content here.", index=0, start_char=0, end_char=18),
            Paragraph(text="More good content.", index=1, start_char=19, end_char=37),
        ]
        doc = ParsedDocument(
            file_path="partial.pdf",
            file_type="pdf",
            raw_text="Good content here.\nMore good content.",
            paragraphs=paras,
            parse_status="partial",
            error_info="failed pages: [3]",
        )
        chunks = Chunker().chunk(doc)
        assert len(chunks) >= 1
        # Chunks should contain the available content
        all_text = " ".join(c.text for c in chunks)
        assert "Good content" in all_text
        # Offsets must be valid
        for c in chunks:
            located = doc.raw_text[c.char_start : c.char_end]
            assert located in c.text

    def test_partial_doc_not_rejected_like_failed(self) -> None:
        """partial != failed: chunker must NOT return empty for partial docs."""
        paras = [
            Paragraph(text="Surviving paragraph.", index=0, start_char=0, end_char=20),
        ]
        doc = ParsedDocument(
            file_path="partial.docx",
            file_type="docx",
            raw_text="Surviving paragraph.",
            paragraphs=paras,
            parse_status="partial",
            error_info="failed paragraphs at indices: [1]",
        )
        chunks = Chunker().chunk(doc)
        assert len(chunks) == 1
        assert chunks[0].text == "Surviving paragraph."


class TestChunkResultToChunkModelMapping:
    """Cross-layer guard: ChunkResult fields must align with S1 ChunkModel.

    If S1 renames or removes a column, this test will catch the mismatch
    before S3 attempts to write ChunkResult data into the database.
    """

    def test_all_chunk_fields_present_in_orm(self) -> None:
        from dataclasses import fields as dc_fields

        from opendocs.domain.models import ChunkModel
        from opendocs.indexing.chunker import ChunkResult

        orm_columns = {c.key for c in ChunkModel.__table__.columns}
        # ChunkResult fields that map 1:1 to ChunkModel columns
        chunk_fields = {f.name for f in dc_fields(ChunkResult)}
        # ORM has extra housekeeping columns not in ChunkResult
        orm_only = {"created_at", "updated_at"}

        missing_in_orm = chunk_fields - orm_columns - orm_only
        assert not missing_in_orm, (
            f"ChunkResult has fields not in ChunkModel: {missing_in_orm}. "
            "Either add the column to ChunkModel or remove from ChunkResult."
        )

        missing_in_result = (orm_columns - orm_only) - chunk_fields
        assert not missing_in_result, (
            f"ChunkModel has columns not in ChunkResult: {missing_in_result}. "
            "Either add the field to ChunkResult or it won't be populated in S3."
        )
