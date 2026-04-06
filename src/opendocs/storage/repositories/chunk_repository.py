"""Repository for chunk persistence."""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from opendocs.domain.models import ChunkModel, DocumentModel
from opendocs.exceptions import DeleteNotAllowedError
from opendocs.utils.time import utcnow_naive


@dataclass(frozen=True)
class SearchChunkRecord:
    """Read model for S4 search scoring and evidence assembly."""

    chunk_id: str
    doc_id: str
    text: str
    char_start: int
    char_end: int
    page_no: int | None
    paragraph_start: int | None
    paragraph_end: int | None
    heading_path: str | None
    title: str
    display_path: str
    modified_at: datetime


class ChunkRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, chunk: ChunkModel) -> ChunkModel:
        self._session.add(chunk)
        self._session.flush()
        return chunk

    def get_by_id(self, chunk_id: str) -> ChunkModel | None:
        return self._session.get(ChunkModel, chunk_id)

    def list_by_document(self, doc_id: str) -> list[ChunkModel]:
        statement = (
            select(ChunkModel)
            .where(ChunkModel.doc_id == doc_id)
            .order_by(ChunkModel.chunk_index.asc())
        )
        return list(self._session.scalars(statement))

    def get_by_document_index(self, doc_id: str, chunk_index: int) -> ChunkModel | None:
        statement = select(ChunkModel).where(
            ChunkModel.doc_id == doc_id,
            ChunkModel.chunk_index == chunk_index,
        )
        return self._session.scalar(statement)

    def list_chunk_ids_by_doc_ids(self, doc_ids: Collection[str]) -> set[str]:
        if not doc_ids:
            return set()
        statement = (
            select(ChunkModel.chunk_id)
            .join(DocumentModel, ChunkModel.doc_id == DocumentModel.doc_id)
            .where(DocumentModel.doc_id.in_(tuple(doc_ids)))
            .where(DocumentModel.is_deleted_from_fs.is_(False))
        )
        return {chunk_id for chunk_id in self._session.scalars(statement)}

    def load_search_records(self, chunk_ids: Collection[str]) -> dict[str, SearchChunkRecord]:
        """Batch-load candidate chunks with their active document facts.

        Search owns ranking and evidence formatting, but the persistence layer
        owns how chunk/document rows are assembled into a stable read model.
        """
        if not chunk_ids:
            return {}

        statement = (
            select(
                ChunkModel.chunk_id,
                ChunkModel.doc_id,
                ChunkModel.text,
                ChunkModel.char_start,
                ChunkModel.char_end,
                ChunkModel.page_no,
                ChunkModel.paragraph_start,
                ChunkModel.paragraph_end,
                ChunkModel.heading_path,
                DocumentModel.title,
                DocumentModel.display_path,
                DocumentModel.modified_at,
            )
            .join(DocumentModel, ChunkModel.doc_id == DocumentModel.doc_id)
            .where(ChunkModel.chunk_id.in_(tuple(chunk_ids)))
            .where(DocumentModel.is_deleted_from_fs.is_(False))
        )
        rows = self._session.execute(statement).all()
        return {
            row.chunk_id: SearchChunkRecord(
                chunk_id=row.chunk_id,
                doc_id=row.doc_id,
                text=row.text,
                char_start=row.char_start,
                char_end=row.char_end,
                page_no=row.page_no,
                paragraph_start=row.paragraph_start,
                paragraph_end=row.paragraph_end,
                heading_path=row.heading_path,
                title=row.title,
                display_path=row.display_path,
                modified_at=row.modified_at,
            )
            for row in rows
        }

    def update_text(
        self,
        chunk_id: str,
        *,
        text: str,
        char_start: int | None = None,
        char_end: int | None = None,
    ) -> bool:
        chunk = self.get_by_id(chunk_id)
        if chunk is None:
            return False
        chunk.text = text
        if char_start is not None:
            chunk.char_start = char_start
        if char_end is not None:
            chunk.char_end = char_end
        chunk.updated_at = utcnow_naive()
        self._session.flush()
        return True

    def delete_by_doc_id(self, doc_id: str, *, allow_delete: bool = False) -> int:
        """Delete all chunks belonging to a document. Returns count of deleted rows."""
        if not allow_delete:
            raise DeleteNotAllowedError(
                "delete is disabled by default; pass allow_delete=True explicitly"
            )
        chunks = self.list_by_document(doc_id)
        for chunk in chunks:
            self._session.delete(chunk)
        self._session.flush()
        return len(chunks)

    def delete(self, chunk_id: str, *, allow_delete: bool = False) -> bool:
        if not allow_delete:
            raise DeleteNotAllowedError(
                "delete is disabled by default; pass allow_delete=True explicitly"
            )
        chunk = self.get_by_id(chunk_id)
        if chunk is None:
            return False
        self._session.delete(chunk)
        self._session.flush()
        return True
