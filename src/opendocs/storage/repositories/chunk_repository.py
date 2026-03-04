"""Repository for chunk persistence."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from opendocs.domain.models import ChunkModel


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
        self._session.flush()
        return True

    def delete(self, chunk_id: str) -> bool:
        chunk = self.get_by_id(chunk_id)
        if chunk is None:
            return False
        self._session.delete(chunk)
        self._session.flush()
        return True
