"""FTS5 trigram search — single-path, no LIKE fallback (ADR-0012)."""

from __future__ import annotations

import logging

from sqlalchemy import text as sa_text
from sqlalchemy.orm import Session

from opendocs.retrieval.query_preprocessor import PreparedQuery, QueryPreprocessor

logger = logging.getLogger(__name__)

_SCHEMA_OR_DB_ERROR_TOKENS = (
    "no such table",
    "no such column",
    "has no column named",
    "no such index",
    "unknown tokenizer",
    "database disk image is malformed",
    "database schema has changed",
    "malformed database schema",
    "unable to open database file",
)

_MATCH_SYNTAX_ERROR_TOKENS = (
    "fts5: syntax error",
    "malformed match expression",
    "unterminated string",
    "syntax error near",
)


class FtsSearcher:
    """Execute trigram FTS5 MATCH queries."""

    def __init__(self, preprocessor: QueryPreprocessor | None = None) -> None:
        self._preprocessor = preprocessor or QueryPreprocessor()

    def search(
        self,
        session: Session,
        query: str,
        *,
        doc_ids: set[str] | None = None,
        limit: int = 36,
    ) -> list[tuple[str, str, float]]:
        """Search FTS5 trigram index.

        Returns list of (chunk_id, doc_id, bm25_score).
        bm25_score is negative (more negative = better match).
        Returns empty list if query is too short for trigram or no matches.
        """
        prepared = self._preprocessor.prepare(query)
        return self.search_prepared(
            session,
            prepared,
            doc_ids=doc_ids,
            limit=limit,
        )

    def search_prepared(
        self,
        session: Session,
        prepared: PreparedQuery,
        *,
        doc_ids: set[str] | None = None,
        limit: int = 36,
    ) -> list[tuple[str, str, float]]:
        """Search FTS5 using a pre-normalized query object."""
        variants = [variant for variant in prepared.variants if variant.fts_query is not None]
        if not variants:
            return []

        try:
            merged: dict[str, tuple[str, float]] = {}
            for variant in variants:
                rows = self._execute_match(
                    session,
                    variant.fts_query,
                    doc_ids=doc_ids,
                    limit=limit,
                )
                for chunk_id, doc_id, score in rows:
                    current = merged.get(chunk_id)
                    if current is None or score < current[1]:
                        merged[chunk_id] = (doc_id, score)

            ranked = [
                (chunk_id, doc_id, score)
                for chunk_id, (doc_id, score) in merged.items()
            ]
            ranked.sort(key=lambda row: row[2])
            return ranked[:limit]
        except Exception as exc:
            exc_msg = str(exc)
            exc_lower = exc_msg.lower()
            if any(token in exc_lower for token in _SCHEMA_OR_DB_ERROR_TOKENS):
                logger.error("FTS query error (not a match issue): %s", exc_msg)
                raise
            if any(token in exc_lower for token in _MATCH_SYNTAX_ERROR_TOKENS):
                logger.debug("FTS MATCH empty or syntax issue for %r: %s", prepared.variants, exc_msg)
                return []
            logger.error("Unexpected FTS query error: %s", exc_msg)
            raise

    @staticmethod
    def _execute_match(
        session: Session,
        query: str | None,
        *,
        doc_ids: set[str] | None,
        limit: int,
    ) -> list[tuple[str, str, float]]:
        if query is None:
            return []
        if doc_ids is not None and doc_ids:
            placeholders = ", ".join(f":did{i}" for i in range(len(doc_ids)))
            sql = sa_text(
                f"SELECT chunk_id, doc_id, bm25(chunk_fts) AS score "
                f"FROM chunk_fts "
                f"WHERE chunk_fts MATCH :query "
                f"AND doc_id IN ({placeholders}) "
                f"ORDER BY score "
                f"LIMIT :lim"
            )
            params: dict[str, object] = {"query": query, "lim": limit}
            for i, did in enumerate(doc_ids):
                params[f"did{i}"] = did
        else:
            sql = sa_text(
                "SELECT chunk_id, doc_id, bm25(chunk_fts) AS score "
                "FROM chunk_fts "
                "WHERE chunk_fts MATCH :query "
                "ORDER BY score "
                "LIMIT :lim"
            )
            params = {"query": query, "lim": limit}

        rows = session.execute(sql, params).fetchall()
        return [(row[0], row[1], float(row[2])) for row in rows]
