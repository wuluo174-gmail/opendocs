"""Stage-scoped acceptance corpus owners for S4 verification."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from opendocs.retrieval.stage_acceptance_capture_cases import load_s4_acceptance_capture_cases
from opendocs.retrieval.stage_asset_loader import read_stage_asset_text
from opendocs.retrieval.stage_search_corpus import materialize_s4_search_corpus

S4_ACCEPTANCE_CORPORA_ASSET_REF = "src/opendocs/retrieval/assets/s4_acceptance_corpora.json"


@dataclass(frozen=True)
class StageGeneratedAcceptanceCorpus:
    mode: str
    manifest_label: str

    def materialize(self, target_dir: Path) -> tuple[Path, str]:
        return materialize_s4_search_corpus(target_dir), self.manifest_label


@dataclass(frozen=True)
class StageFixtureAcceptanceCorpus:
    mode: str
    relative_path: str
    required_documents: tuple[str, ...]

    def resolve(self, repo_root: Path) -> Path:
        corpus_dir = (repo_root / self.relative_path).resolve()
        if not corpus_dir.is_dir():
            raise FileNotFoundError(f"S4 fixture corpus directory not found: {corpus_dir}")
        missing = [name for name in self.required_documents if not (corpus_dir / name).is_file()]
        if missing:
            raise FileNotFoundError(
                f"S4 fixture corpus missing required documents: {', '.join(sorted(missing))}"
            )
        return corpus_dir


@dataclass(frozen=True)
class StageAcceptanceCorpora:
    tc005: StageGeneratedAcceptanceCorpus
    tc018: StageFixtureAcceptanceCorpus


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


@lru_cache(maxsize=1)
def load_s4_acceptance_corpora() -> StageAcceptanceCorpora:
    payload = json.loads(read_stage_asset_text(S4_ACCEPTANCE_CORPORA_ASSET_REF))
    if not isinstance(payload, dict):
        raise ValueError("S4 acceptance corpora must be an object")
    tc005 = _parse_tc005_corpus(payload.get("tc005"))
    tc018 = _parse_tc018_corpus(payload.get("tc018"))
    return StageAcceptanceCorpora(tc005=tc005, tc018=tc018)


def resolve_s4_tc018_corpus_dir() -> Path:
    return load_s4_acceptance_corpora().tc018.resolve(repo_root())


def materialize_s4_tc005_acceptance_corpus(target_dir: Path) -> tuple[Path, str]:
    return load_s4_acceptance_corpora().tc005.materialize(target_dir)


def _parse_tc005_corpus(raw_spec: object) -> StageGeneratedAcceptanceCorpus:
    if not isinstance(raw_spec, dict):
        raise ValueError("S4 TC-005 acceptance corpus must be an object")
    mode = str(raw_spec.get("mode", "")).strip()
    manifest_label = str(raw_spec.get("manifest_label", "")).strip()
    if mode != "generated":
        raise ValueError(f"S4 TC-005 acceptance corpus has invalid mode: {mode!r}")
    if not manifest_label:
        raise ValueError("S4 TC-005 acceptance corpus missing manifest_label")
    return StageGeneratedAcceptanceCorpus(mode=mode, manifest_label=manifest_label)


def _parse_tc018_corpus(raw_spec: object) -> StageFixtureAcceptanceCorpus:
    if not isinstance(raw_spec, dict):
        raise ValueError("S4 TC-018 acceptance corpus must be an object")
    mode = str(raw_spec.get("mode", "")).strip()
    relative_path = str(raw_spec.get("relative_path", "")).strip()
    required_documents = _parse_required_documents(raw_spec.get("required_documents"))
    if mode != "fixture":
        raise ValueError(f"S4 TC-018 acceptance corpus has invalid mode: {mode!r}")
    if not relative_path:
        raise ValueError("S4 TC-018 acceptance corpus missing relative_path")
    expected_documents = {
        case.expected_file_name for case in load_s4_acceptance_capture_cases().tc018
    }
    if set(required_documents) != expected_documents:
        raise ValueError(
            "S4 TC-018 acceptance corpus coverage drift: "
            f"{sorted(required_documents)} != {sorted(expected_documents)}"
        )
    return StageFixtureAcceptanceCorpus(
        mode=mode,
        relative_path=relative_path,
        required_documents=required_documents,
    )


def _parse_required_documents(raw_documents: object) -> tuple[str, ...]:
    if not isinstance(raw_documents, list):
        raise ValueError("S4 TC-018 acceptance corpus required_documents must be an array")
    documents: list[str] = []
    seen_documents: set[str] = set()
    for raw_document in raw_documents:
        document = str(raw_document).strip()
        if not document:
            raise ValueError("S4 TC-018 acceptance corpus document names must be non-empty")
        if document in seen_documents:
            raise ValueError(f"duplicate S4 TC-018 acceptance corpus document: {document}")
        seen_documents.add(document)
        documents.append(document)
    if len(documents) != 2:
        raise ValueError(
            f"S4 TC-018 acceptance corpus must declare exactly 2 documents, found {len(documents)}"
        )
    return tuple(documents)
