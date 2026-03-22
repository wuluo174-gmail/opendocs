"""Repository for scan run persistence."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from opendocs.domain.models import ScanRunModel


class ScanRunRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, scan_run: ScanRunModel) -> ScanRunModel:
        self._session.add(scan_run)
        self._session.flush()
        return scan_run

    def get_by_id(self, scan_run_id: str) -> ScanRunModel | None:
        return self._session.get(ScanRunModel, scan_run_id)

    def list_by_source(self, source_root_id: str) -> list[ScanRunModel]:
        statement = (
            select(ScanRunModel)
            .where(ScanRunModel.source_root_id == source_root_id)
            .order_by(ScanRunModel.started_at.desc())
        )
        return list(self._session.scalars(statement))

    def update_status(
        self,
        scan_run: ScanRunModel,
        *,
        status: str,
        included_count: int = 0,
        excluded_count: int = 0,
        unsupported_count: int = 0,
        failed_count: int = 0,
        error_summary: list[dict[str, str]] | None = None,
        finished_at: object = None,
    ) -> ScanRunModel:
        from opendocs.utils.time import utcnow_naive

        scan_run.status = status
        scan_run.included_count = included_count
        scan_run.excluded_count = excluded_count
        scan_run.unsupported_count = unsupported_count
        scan_run.failed_count = failed_count
        if error_summary is not None:
            scan_run.error_summary_json = error_summary  # type: ignore[assignment]
        scan_run.finished_at = finished_at or utcnow_naive()
        self._session.flush()
        return scan_run
