"""Repository for document persistence."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from opendocs.domain.models import DocumentModel


class DocumentRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, document: DocumentModel) -> DocumentModel:
        self._session.add(document)
        self._session.flush()
        return document

    def get_by_id(self, doc_id: str) -> DocumentModel | None:
        return self._session.get(DocumentModel, doc_id)

    def get_by_path(self, path: str) -> DocumentModel | None:
        statement = select(DocumentModel).where(DocumentModel.path == path)
        return self._session.scalar(statement)

    def list_all(self, limit: int = 100) -> list[DocumentModel]:
        statement = select(DocumentModel).order_by(DocumentModel.path.asc()).limit(limit)
        return list(self._session.scalars(statement))

    def update_title(self, doc_id: str, title: str) -> bool:
        document = self.get_by_id(doc_id)
        if document is None:
            return False
        document.title = title
        self._session.flush()
        return True

    def delete(self, doc_id: str) -> bool:
        document = self.get_by_id(doc_id)
        if document is None:
            return False
        self._session.delete(document)
        self._session.flush()
        return True
