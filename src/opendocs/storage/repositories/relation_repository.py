"""Repository for relation edge persistence."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from opendocs.domain.models import RelationEdgeModel


class RelationRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, relation_edge: RelationEdgeModel) -> RelationEdgeModel:
        self._session.add(relation_edge)
        self._session.flush()
        return relation_edge

    def get_by_id(self, edge_id: str) -> RelationEdgeModel | None:
        return self._session.get(RelationEdgeModel, edge_id)

    def list_by_source(self, src_type: str, src_id: str) -> list[RelationEdgeModel]:
        statement = select(RelationEdgeModel).where(
            RelationEdgeModel.src_type == src_type,
            RelationEdgeModel.src_id == src_id,
        )
        return list(self._session.scalars(statement))

    def update_weight(self, edge_id: str, weight: float) -> bool:
        relation_edge = self.get_by_id(edge_id)
        if relation_edge is None:
            return False
        relation_edge.weight = weight
        self._session.flush()
        return True

    def delete(self, edge_id: str, *, allow_delete: bool = False) -> bool:
        if not allow_delete:
            raise PermissionError(
                "delete is disabled by default; pass allow_delete=True explicitly"
            )
        relation_edge = self.get_by_id(edge_id)
        if relation_edge is None:
            return False
        self._session.delete(relation_edge)
        self._session.flush()
        return True
