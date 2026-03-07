"""Repository for document persistence."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from opendocs.domain.models import DocumentModel
from opendocs.exceptions import DeleteNotAllowedError
from opendocs.utils.time import utcnow_naive


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

    def list_all(self, *, limit: int | None = None) -> list[DocumentModel]:
        statement = select(DocumentModel).order_by(DocumentModel.path.asc())
        if limit is not None:
            statement = statement.limit(limit)
        return list(self._session.scalars(statement))

    def update_title(self, doc_id: str, title: str) -> bool:
        document = self.get_by_id(doc_id)
        if document is None:
            return False
        document.title = title
        # NOTE: modified_at is file-system mtime (§8.1.1), not record-update time.
        # Do not change it here; audit logs track record-level mutations.
        self._session.flush()
        return True

    def update_indexed_at(self, doc_id: str, indexed_at: datetime | None = None) -> bool:
        document = self.get_by_id(doc_id)
        if document is None:
            return False
        document.indexed_at = indexed_at or utcnow_naive()
        # NOTE: modified_at is file-system mtime (§8.1.1); indexing does not change it.
        self._session.flush()
        return True

    def mark_deleted_from_fs(self, doc_id: str, *, deleted: bool = True) -> bool:
        document = self.get_by_id(doc_id)
        if document is None:
            return False
        document.is_deleted_from_fs = deleted
        # NOTE: modified_at is file-system mtime (§8.1.1); this flag tracks FS state.
        self._session.flush()
        return True

    def delete(self, doc_id: str, *, allow_delete: bool = False) -> bool:
        if not allow_delete:
            raise DeleteNotAllowedError(
                "delete is disabled by default; pass allow_delete=True explicitly"
            )
        document = self.get_by_id(doc_id)
        if document is None:
            return False
        self._session.delete(document)
        self._session.flush()
        return True
