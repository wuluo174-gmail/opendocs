"""Repository for derived index artifact state."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from opendocs.domain.models import IndexArtifactModel
from opendocs.utils.time import utcnow_naive

_UNSET = object()


class IndexArtifactRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, artifact_name: str) -> IndexArtifactModel | None:
        return self._session.get(IndexArtifactModel, artifact_name)

    def upsert(
        self,
        artifact_name: str,
        *,
        status: str,
        artifact_path: str,
        embedder_model: str,
        embedder_dim: int,
        embedder_signature: str,
        last_error: str | None | object = _UNSET,
        last_reason: str | None | object = _UNSET,
        last_built_at: datetime | None | object = _UNSET,
    ) -> IndexArtifactModel:
        artifact = self.get(artifact_name)
        if artifact is None:
            artifact = IndexArtifactModel(
                artifact_name=artifact_name,
                status=status,
                artifact_path=artifact_path,
                embedder_model=embedder_model,
                embedder_dim=embedder_dim,
                embedder_signature=embedder_signature,
            )
            self._session.add(artifact)

        artifact.status = status
        artifact.artifact_path = artifact_path
        artifact.embedder_model = embedder_model
        artifact.embedder_dim = embedder_dim
        artifact.embedder_signature = embedder_signature
        artifact.updated_at = utcnow_naive()

        if last_error is not _UNSET:
            artifact.last_error = last_error
        if last_reason is not _UNSET:
            artifact.last_reason = last_reason
        if last_built_at is not _UNSET:
            artifact.last_built_at = last_built_at

        self._session.flush()
        return artifact
