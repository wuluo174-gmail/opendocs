"""Repository for derived index artifact state."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import case, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from opendocs.domain.models import IndexArtifactGenerationModel, IndexArtifactModel
from opendocs.utils.time import utcnow_naive

_UNSET = object()
_PUBLIC_FRESHNESS_STATUSES = frozenset({"stale", "ready", "failed"})


class IndexArtifactRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, artifact_name: str) -> IndexArtifactModel | None:
        return self._session.get(IndexArtifactModel, artifact_name)

    @staticmethod
    def _assert_public_status(status: str) -> None:
        if status not in _PUBLIC_FRESHNESS_STATUSES:
            raise ValueError(
                f"invalid public artifact status: {status!r}; "
                f"expected one of {sorted(_PUBLIC_FRESHNESS_STATUSES)}"
            )

    def get_generation(
        self,
        artifact_name: str,
        generation: int,
    ) -> IndexArtifactGenerationModel | None:
        if generation <= 0:
            return None
        return self._session.get(
            IndexArtifactGenerationModel,
            {"artifact_name": artifact_name, "generation": generation},
        )

    def get_committed_generation(
        self,
        artifact_name: str,
    ) -> IndexArtifactGenerationModel | None:
        stmt = (
            select(IndexArtifactGenerationModel)
            .where(IndexArtifactGenerationModel.artifact_name == artifact_name)
            .where(IndexArtifactGenerationModel.state == "committed")
            .limit(1)
        )
        return self._session.scalar(stmt)

    def list_generations(
        self,
        artifact_name: str,
        *,
        include_deleted: bool = False,
    ) -> list[IndexArtifactGenerationModel]:
        stmt = (
            select(IndexArtifactGenerationModel)
            .where(IndexArtifactGenerationModel.artifact_name == artifact_name)
            .order_by(IndexArtifactGenerationModel.generation.desc())
        )
        if not include_deleted:
            stmt = stmt.where(IndexArtifactGenerationModel.state != "deleted")
        return list(self._session.scalars(stmt).all())

    def list_gc_due_generations(
        self,
        artifact_name: str,
        *,
        delete_before: datetime,
    ) -> list[IndexArtifactGenerationModel]:
        stmt = (
            select(IndexArtifactGenerationModel)
            .where(IndexArtifactGenerationModel.artifact_name == artifact_name)
            .where(IndexArtifactGenerationModel.state == "retained")
            .where(IndexArtifactGenerationModel.delete_after.is_not(None))
            .where(IndexArtifactGenerationModel.delete_after < delete_before)
            .order_by(IndexArtifactGenerationModel.generation.asc())
        )
        return list(self._session.scalars(stmt).all())

    def next_gc_due_at(
        self,
        artifact_name: str,
    ) -> datetime | None:
        stmt = (
            select(IndexArtifactGenerationModel.delete_after)
            .where(IndexArtifactGenerationModel.artifact_name == artifact_name)
            .where(IndexArtifactGenerationModel.state == "retained")
            .where(IndexArtifactGenerationModel.delete_after.is_not(None))
            .order_by(IndexArtifactGenerationModel.delete_after.asc())
            .limit(1)
        )
        return self._session.scalar(stmt)

    def upsert_generation(
        self,
        artifact_name: str,
        *,
        generation: int,
        bundle_path: str,
        state: str,
        committed_at: datetime,
        retired_at: datetime | None = None,
        delete_after: datetime | None = None,
        deleted_at: datetime | None = None,
    ) -> IndexArtifactGenerationModel:
        updated_at = utcnow_naive()
        self._session.execute(
            sqlite_insert(IndexArtifactGenerationModel)
            .values(
                artifact_name=artifact_name,
                generation=generation,
                bundle_path=bundle_path,
                state=state,
                committed_at=committed_at,
                retired_at=retired_at,
                delete_after=delete_after,
                deleted_at=deleted_at,
                updated_at=updated_at,
            )
            .on_conflict_do_update(
                index_elements=["artifact_name", "generation"],
                set_={
                    "bundle_path": bundle_path,
                    "state": state,
                    "committed_at": committed_at,
                    "retired_at": retired_at,
                    "delete_after": delete_after,
                    "deleted_at": deleted_at,
                    "updated_at": updated_at,
                },
            )
        )
        self._session.flush()
        generation_row = self.get_generation(artifact_name, generation)
        assert generation_row is not None
        return generation_row

    def mark_generation_deleted(
        self,
        artifact_name: str,
        *,
        generation: int,
        deleted_at: datetime,
    ) -> bool:
        updated_at = utcnow_naive()
        result = self._session.execute(
            update(IndexArtifactGenerationModel)
            .where(IndexArtifactGenerationModel.artifact_name == artifact_name)
            .where(IndexArtifactGenerationModel.generation == generation)
            .where(IndexArtifactGenerationModel.state != "deleted")
            .values(
                state="deleted",
                deleted_at=deleted_at,
                updated_at=updated_at,
            )
        )
        self._session.flush()
        return int(result.rowcount or 0) == 1

    def ensure_artifact(
        self,
        artifact_name: str,
        *,
        namespace_path: str,
        embedder_model: str,
        embedder_dim: int,
        embedder_signature: str,
    ) -> IndexArtifactModel:
        created_at = utcnow_naive()
        self._session.execute(
            sqlite_insert(IndexArtifactModel)
            .values(
                artifact_name=artifact_name,
                status="stale",
                namespace_path=namespace_path,
                embedder_model=embedder_model,
                embedder_dim=embedder_dim,
                embedder_signature=embedder_signature,
                generation=0,
                updated_at=created_at,
            )
            .on_conflict_do_nothing(index_elements=["artifact_name"])
        )
        self._session.flush()
        artifact = self.get(artifact_name)
        assert artifact is not None
        return artifact

    def upsert(
        self,
        artifact_name: str,
        *,
        status: str,
        namespace_path: str | object = _UNSET,
        embedder_model: str | object = _UNSET,
        embedder_dim: int | object = _UNSET,
        embedder_signature: str | object = _UNSET,
        generation: int | object = _UNSET,
        active_build_token: str | None | object = _UNSET,
        build_started_at: datetime | None | object = _UNSET,
        lease_expires_at: datetime | None | object = _UNSET,
        last_error: str | None | object = _UNSET,
        last_reason: str | None | object = _UNSET,
        last_built_at: datetime | None | object = _UNSET,
    ) -> IndexArtifactModel:
        self._assert_public_status(status)
        artifact = self.get(artifact_name)
        if artifact is None:
            if (
                namespace_path is _UNSET
                or embedder_model is _UNSET
                or embedder_dim is _UNSET
                or embedder_signature is _UNSET
            ):
                raise ValueError(
                    "namespace_path/embedder metadata are required when creating artifact"
                )
            artifact = IndexArtifactModel(
                artifact_name=artifact_name,
                status=status,
                namespace_path=str(namespace_path),
                embedder_model=str(embedder_model),
                embedder_dim=int(embedder_dim),
                embedder_signature=str(embedder_signature),
                generation=0 if generation is _UNSET else int(generation),
            )
            self._session.add(artifact)

        artifact.status = status
        artifact.updated_at = utcnow_naive()

        if namespace_path is not _UNSET:
            artifact.namespace_path = str(namespace_path)
        if embedder_model is not _UNSET:
            artifact.embedder_model = str(embedder_model)
        if embedder_dim is not _UNSET:
            artifact.embedder_dim = int(embedder_dim)
        if embedder_signature is not _UNSET:
            artifact.embedder_signature = str(embedder_signature)
        if generation is not _UNSET:
            artifact.generation = int(generation)
        if active_build_token is not _UNSET:
            artifact.active_build_token = active_build_token
        if build_started_at is not _UNSET:
            artifact.build_started_at = build_started_at
        if lease_expires_at is not _UNSET:
            artifact.lease_expires_at = lease_expires_at
        if last_error is not _UNSET:
            artifact.last_error = last_error
        if last_reason is not _UNSET:
            artifact.last_reason = last_reason
        if last_built_at is not _UNSET:
            artifact.last_built_at = last_built_at

        self._session.flush()
        return artifact

    def try_claim_build(
        self,
        artifact_name: str,
        *,
        namespace_path: str,
        embedder_model: str,
        embedder_dim: int,
        embedder_signature: str,
        build_token: str,
        build_started_at: datetime,
        lease_expires_at: datetime,
        reason: str,
    ) -> bool:
        self.ensure_artifact(
            artifact_name,
            namespace_path=namespace_path,
            embedder_model=embedder_model,
            embedder_dim=embedder_dim,
            embedder_signature=embedder_signature,
        )
        updated_at = utcnow_naive()
        result = self._session.execute(
            update(IndexArtifactModel)
            .where(IndexArtifactModel.artifact_name == artifact_name)
            .where(
                (IndexArtifactModel.active_build_token.is_(None))
                | (IndexArtifactModel.lease_expires_at.is_(None))
                | (IndexArtifactModel.lease_expires_at < build_started_at)
            )
            .values(
                namespace_path=namespace_path,
                active_build_token=build_token,
                build_started_at=build_started_at,
                lease_expires_at=lease_expires_at,
                last_error=None,
                last_reason=reason,
                updated_at=updated_at,
            )
        )
        self._session.flush()
        return int(result.rowcount or 0) == 1

    def complete_build(
        self,
        artifact_name: str,
        *,
        build_token: str,
        reason: str,
        last_built_at: datetime,
        committed_bundle_path: str,
        embedder_model: str,
        embedder_dim: int,
        embedder_signature: str,
        retained_delete_after: datetime | None = None,
    ) -> tuple[bool, str | None]:
        artifact = self.get(artifact_name)
        previous_generation = artifact.generation if artifact is not None else 0
        previous_generation_row = (
            self.get_generation(artifact_name, previous_generation)
            if previous_generation > 0
            else None
        )
        if previous_generation_row is None and previous_generation > 0:
            previous_generation_row = self.get_committed_generation(artifact_name)
        previous_bundle_path = (
            previous_generation_row.bundle_path if previous_generation_row is not None else None
        )
        next_generation = previous_generation + 1
        updated_at = utcnow_naive()
        previous_committed_at = (
            artifact.last_built_at if artifact is not None and artifact.last_built_at is not None else updated_at
        ) if artifact is not None else last_built_at
        result = self._session.execute(
            update(IndexArtifactModel)
            .where(IndexArtifactModel.artifact_name == artifact_name)
            .where(IndexArtifactModel.active_build_token == build_token)
            .values(
                status="ready",
                embedder_model=embedder_model,
                embedder_dim=embedder_dim,
                embedder_signature=embedder_signature,
                generation=next_generation,
                active_build_token=None,
                build_started_at=None,
                lease_expires_at=None,
                last_error=None,
                last_reason=reason,
                last_built_at=last_built_at,
                updated_at=updated_at,
            )
        )
        self._session.flush()
        completed = int(result.rowcount or 0) == 1
        if completed:
            if previous_generation > 0 and previous_bundle_path is not None:
                self.upsert_generation(
                    artifact_name,
                    generation=previous_generation,
                    bundle_path=previous_bundle_path,
                    state="retained",
                    committed_at=previous_committed_at,
                    retired_at=last_built_at,
                    delete_after=retained_delete_after,
                )
            self.upsert_generation(
                artifact_name,
                generation=next_generation,
                bundle_path=committed_bundle_path,
                state="committed",
                committed_at=last_built_at,
            )
        return (
            completed,
            previous_bundle_path if completed and previous_generation > 0 else None,
        )

    def fail_build(
        self,
        artifact_name: str,
        *,
        build_token: str,
        status: str,
        reason: str,
        last_error: str | None,
    ) -> bool:
        self._assert_public_status(status)
        updated_at = utcnow_naive()
        result = self._session.execute(
            update(IndexArtifactModel)
            .where(IndexArtifactModel.artifact_name == artifact_name)
            .where(IndexArtifactModel.active_build_token == build_token)
            .values(
                status=case(
                    (IndexArtifactModel.generation > 0, IndexArtifactModel.status),
                    else_=status,
                ),
                active_build_token=None,
                build_started_at=None,
                lease_expires_at=None,
                last_error=last_error,
                last_reason=reason,
                updated_at=updated_at,
            )
        )
        self._session.flush()
        return int(result.rowcount or 0) == 1

    def expire_build_lease(
        self,
        artifact_name: str,
        *,
        expired_before: datetime,
        reason: str,
    ) -> bool:
        updated_at = utcnow_naive()
        result = self._session.execute(
            update(IndexArtifactModel)
            .where(IndexArtifactModel.artifact_name == artifact_name)
            .where(IndexArtifactModel.active_build_token.is_not(None))
            .where(IndexArtifactModel.lease_expires_at.is_not(None))
            .where(IndexArtifactModel.lease_expires_at < expired_before)
            .values(
                status=case(
                    (IndexArtifactModel.generation > 0, IndexArtifactModel.status),
                    else_="stale",
                ),
                active_build_token=None,
                build_started_at=None,
                lease_expires_at=None,
                last_reason=reason,
                updated_at=updated_at,
            )
        )
        self._session.flush()
        return int(result.rowcount or 0) == 1
