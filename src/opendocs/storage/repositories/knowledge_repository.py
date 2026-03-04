"""Repository for knowledge item persistence."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from opendocs.domain.models import KnowledgeItemModel


class KnowledgeRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, knowledge_item: KnowledgeItemModel) -> KnowledgeItemModel:
        self._session.add(knowledge_item)
        self._session.flush()
        return knowledge_item

    def get_by_id(self, knowledge_id: str) -> KnowledgeItemModel | None:
        return self._session.get(KnowledgeItemModel, knowledge_id)

    def list_by_document(self, doc_id: str) -> list[KnowledgeItemModel]:
        statement = select(KnowledgeItemModel).where(KnowledgeItemModel.doc_id == doc_id)
        return list(self._session.scalars(statement))

    def update_summary(self, knowledge_id: str, summary: str, confidence: float) -> bool:
        knowledge_item = self.get_by_id(knowledge_id)
        if knowledge_item is None:
            return False
        knowledge_item.summary = summary
        knowledge_item.confidence = confidence
        self._session.flush()
        return True

    def delete(self, knowledge_id: str, *, allow_delete: bool = False) -> bool:
        if not allow_delete:
            raise PermissionError(
                "delete is disabled by default; pass allow_delete=True explicitly"
            )
        knowledge_item = self.get_by_id(knowledge_id)
        if knowledge_item is None:
            return False
        self._session.delete(knowledge_item)
        self._session.flush()
        return True
