"""Tests for the Chunker."""

from __future__ import annotations

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


class TestChunkerShortDoc:
    def test_empty_doc(self) -> None:
        doc = _make_doc([], raw_text="")
        chunks = Chunker().chunk(doc)
        assert chunks == []

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
        config = ChunkConfig(max_chars=900, overlap_ratio=0.0, min_chunk_chars=50)
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
                text="A" * 100, index=0, start_char=0, end_char=100,
                heading_path="Intro",
            ),
            Paragraph(
                text="B" * 100, index=1, start_char=101, end_char=201,
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


class TestChunkerLongParagraph:
    def test_long_paragraph_split(self) -> None:
        long_text = "X" * 2000
        paras = [
            Paragraph(text=long_text, index=0, start_char=0, end_char=2000),
        ]
        doc = _make_doc(paras, raw_text=long_text)
        config = ChunkConfig(max_chars=900, overlap_ratio=0.0, min_chunk_chars=50)
        chunks = Chunker().chunk(doc, config)

        assert len(chunks) >= 3  # 2000 / 900 ≈ 3
        for c in chunks:
            assert c.paragraph_start == 0
            assert c.paragraph_end == 0


class TestChunkerOverlap:
    def test_overlap_present(self) -> None:
        paras = [
            Paragraph(text="A" * 500, index=0, start_char=0, end_char=500),
            Paragraph(text="B" * 500, index=1, start_char=501, end_char=1001),
        ]
        doc = _make_doc(paras)
        config = ChunkConfig(max_chars=600, overlap_ratio=0.12, min_chunk_chars=50)
        chunks = Chunker().chunk(doc, config)

        assert len(chunks) >= 2
        # Second chunk should start with overlap from first
        if len(chunks) >= 2:
            # The overlap text from end of first chunk should appear at start of second
            overlap_len = int(600 * 0.12)
            tail_of_first = chunks[0].text[-overlap_len:]
            assert chunks[1].text.startswith(tail_of_first)


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
                text="Content", index=0, start_char=0, end_char=7,
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
        assert chunks[0].token_estimate == len(chunks[0].text)
