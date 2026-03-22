"""Retrieval package — S4 hybrid search, filters, evidence, and citation."""

from opendocs.retrieval.dense_searcher import DenseSearcher
from opendocs.retrieval.embedder import LocalNgramEmbedder
from opendocs.retrieval.evidence import Citation, SearchResponse, SearchResult
from opendocs.retrieval.evidence_locator import EvidenceLocation, EvidenceLocator
from opendocs.retrieval.filters import SearchFilter
from opendocs.retrieval.fts_searcher import FtsSearcher
from opendocs.retrieval.query_preprocessor import PreparedQuery, QueryPreprocessor
from opendocs.retrieval.rerank import ScoreBreakdown
from opendocs.retrieval.search_pipeline import SearchPipeline

__all__ = [
    "Citation",
    "DenseSearcher",
    "EvidenceLocator",
    "EvidenceLocation",
    "FtsSearcher",
    "LocalNgramEmbedder",
    "PreparedQuery",
    "QueryPreprocessor",
    "ScoreBreakdown",
    "SearchFilter",
    "SearchPipeline",
    "SearchResponse",
    "SearchResult",
]
