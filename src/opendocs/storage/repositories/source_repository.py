"""Repository for source root persistence."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from opendocs.domain.models import SourceRootModel
from opendocs.exceptions import DeleteNotAllowedError
from opendocs.utils.time import utcnow_naive

INDEX_RELEVANT_SOURCE_FIELDS = frozenset(
    {
        "exclude_rules_json",
        "default_category",
        "default_tags_json",
        "default_sensitivity",
        "recursive",
    }
)


class SourceRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, source: SourceRootModel) -> SourceRootModel:
        self._session.add(source)
        self._session.flush()
        return source

    def get_by_id(self, source_root_id: str) -> SourceRootModel | None:
        return self._session.get(SourceRootModel, source_root_id)

    def get_by_path(self, path: str) -> SourceRootModel | None:
        statement = select(SourceRootModel).where(SourceRootModel.path == path)
        return self._session.scalar(statement)

    def list_active(self) -> list[SourceRootModel]:
        statement = (
            select(SourceRootModel)
            .where(SourceRootModel.is_active.is_(True))
            .order_by(SourceRootModel.path.asc())
        )
        return list(self._session.scalars(statement))

    def list_all(self) -> list[SourceRootModel]:
        statement = select(SourceRootModel).order_by(SourceRootModel.path.asc())
        return list(self._session.scalars(statement))

    def update_exclude_rules(self, source_root_id: str, rules_json: dict[str, object]) -> bool:
        source = self.get_by_id(source_root_id)
        if source is None:
            return False
        source.exclude_rules_json = rules_json  # type: ignore[assignment]
        source.updated_at = utcnow_naive()
        self._session.flush()
        return True

    def update(self, source: SourceRootModel, **changes: object) -> bool:
        allowed_fields = {
            "label",
            "exclude_rules_json",
            "default_category",
            "default_tags_json",
            "default_sensitivity",
            "recursive",
            "is_active",
        }
        unknown_fields = set(changes) - allowed_fields
        if unknown_fields:
            field_list = ", ".join(sorted(unknown_fields))
            raise ValueError(f"unsupported source update fields: {field_list}")

        changed = False
        requires_reindex = False
        for field, value in changes.items():
            if getattr(source, field) == value:
                continue
            setattr(source, field, value)
            changed = True
            if field in INDEX_RELEVANT_SOURCE_FIELDS:
                requires_reindex = True

        if not changed:
            return False

        if requires_reindex:
            source.source_config_rev += 1
        source.updated_at = utcnow_naive()
        self._session.flush()
        return True

    def deactivate(self, source_root_id: str) -> bool:
        source = self.get_by_id(source_root_id)
        if source is None:
            return False
        source.is_active = False
        source.updated_at = utcnow_naive()
        self._session.flush()
        return True

    def delete(self, source_root_id: str, *, allow_delete: bool = False) -> bool:
        if not allow_delete:
            raise DeleteNotAllowedError(
                "delete is disabled by default; pass allow_delete=True explicitly"
            )
        source = self.get_by_id(source_root_id)
        if source is None:
            return False
        self._session.delete(source)
        self._session.flush()
        return True
