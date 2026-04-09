"""Shared runtime owner for S3 semantic lifecycle management."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from sqlalchemy.engine import Engine

from opendocs.config.settings import RetrievalSettings
from opendocs.exceptions import RuntimeClosedError
from opendocs.indexing.semantic_indexer import SemanticIndexer, resolve_semantic_namespace_path

if TYPE_CHECKING:
    from opendocs.app.index_service import IndexService
    from opendocs.app.qa_service import QAService
    from opendocs.app.search_service import SearchService


@dataclass(frozen=True)
class _RuntimeKey:
    database_identity: str
    namespace_path: str | None


class _RuntimeOwner:
    """Process-local shared owner keyed by runtime namespace identity."""

    def __init__(
        self,
        engine: Engine,
        *,
        hnsw_path: Path | None,
        generation_gc_idle_poll_seconds: float,
    ) -> None:
        self.semantic_indexer = SemanticIndexer(
            engine,
            hnsw_path=hnsw_path,
            enable_generation_gc_owner=True,
            generation_gc_idle_poll_seconds=generation_gc_idle_poll_seconds,
        )
        self._refcount = 0
        self._lock = threading.Lock()

    def acquire(self, *, generation_gc_idle_poll_seconds: float) -> None:
        with self._lock:
            self._refcount += 1
        self.semantic_indexer.tighten_generation_gc_idle_poll_seconds(
            generation_gc_idle_poll_seconds
        )

    def release(self) -> bool:
        with self._lock:
            if self._refcount <= 0:
                return False
            self._refcount -= 1
            return self._refcount == 0


class OpenDocsRuntime:
    """Own one runtime-scoped semantic indexer and its background lifecycle workers."""

    _registry_lock: ClassVar[threading.Lock] = threading.Lock()
    _owners: ClassVar[dict[_RuntimeKey, _RuntimeOwner]] = {}

    @staticmethod
    def _resolve_database_identity(engine: Engine) -> str:
        database_path = getattr(engine.url, "database", None)
        if database_path and database_path != ":memory:":
            return str(Path(database_path).expanduser().resolve())
        return f"engine:{id(engine)}"

    def __init__(
        self,
        engine: Engine,
        *,
        hnsw_path: Path | None = None,
        generation_gc_idle_poll_seconds: float = 30.0,
    ) -> None:
        self._engine = engine
        self._closed = False
        resolved_hnsw_path = resolve_semantic_namespace_path(engine, preferred_path=hnsw_path)
        self._key = _RuntimeKey(
            database_identity=self._resolve_database_identity(engine),
            namespace_path=str(resolved_hnsw_path) if resolved_hnsw_path is not None else None,
        )

        with self._registry_lock:
            owner = self._owners.get(self._key)
            if owner is None:
                owner = _RuntimeOwner(
                    engine,
                    hnsw_path=resolved_hnsw_path,
                    generation_gc_idle_poll_seconds=generation_gc_idle_poll_seconds,
                )
                self._owners[self._key] = owner
            owner.acquire(generation_gc_idle_poll_seconds=generation_gc_idle_poll_seconds)
            self._owner = owner

    @property
    def is_closed(self) -> bool:
        return self._closed

    def ensure_open(self) -> None:
        if self._closed:
            raise RuntimeClosedError("runtime has been closed and can no longer serve requests")

    @property
    def engine(self) -> Engine:
        self.ensure_open()
        return self._engine

    @property
    def semantic_indexer(self) -> SemanticIndexer:
        self.ensure_open()
        return self._owner.semantic_indexer

    @property
    def hnsw_path(self) -> Path | None:
        self.ensure_open()
        return self._owner.semantic_indexer.hnsw_path

    def build_index_service(self, *, watch_changes: bool = True) -> IndexService:
        self.ensure_open()
        from opendocs.app.index_service import IndexService

        return IndexService(self, watch_changes=watch_changes)

    def build_search_service(self, *, settings: RetrievalSettings | None = None) -> SearchService:
        self.ensure_open()
        from opendocs.app.search_service import SearchService

        return SearchService(self, settings=settings)

    def build_qa_service(
        self,
        *,
        search_service: SearchService | None = None,
    ) -> QAService:
        self.ensure_open()
        from opendocs.app.qa_service import QAService

        return QAService(self, search_service=search_service)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True

        owner_to_close: _RuntimeOwner | None = None
        with self._registry_lock:
            if self._owner.release():
                self._owners.pop(self._key, None)
                owner_to_close = self._owner

        if owner_to_close is not None:
            owner_to_close.semantic_indexer.close()

    def __enter__(self) -> OpenDocsRuntime:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def __del__(self) -> None:  # pragma: no cover - best-effort cleanup
        try:
            self.close()
        except Exception:
            pass
