"""Deterministic artifact capture helpers for S4 acceptance evidence."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from opendocs.app.index_service import IndexService
from opendocs.app.search_service import SearchService
from opendocs.app.source_service import SourceService
from opendocs.domain.document_metadata import DocumentMetadata
from opendocs.retrieval.stage_acceptance_corpora import (
    materialize_s4_tc005_acceptance_corpus,
    resolve_s4_tc018_corpus_dir,
)
from opendocs.retrieval.stage_acceptance_capture_cases import (
    StageTc005CaptureCase,
    load_s4_acceptance_capture_cases,
)
from opendocs.retrieval.filters import SearchFilter
from opendocs.retrieval.stage_acceptance_provenance import (
    build_s4_tc005_input_provenance,
    build_s4_tc018_input_provenance,
)
from opendocs.retrieval.stage_filter_cases import StageFilterCase, load_s4_search_filter_cases
from opendocs.retrieval.stage_golden_queries import StageGoldenQuery, load_s4_hybrid_search_queries
from opendocs.retrieval.stage_search_corpus import build_s4_search_source_defaults
from opendocs.storage.db import build_sqlite_engine, init_db
from opendocs.ui.search_window import SearchWindow

if TYPE_CHECKING:
    from PySide6.QtWidgets import QApplication, QListWidgetItem


@dataclass(frozen=True)
class CaptureSpec:
    slug: str
    query: str
    expected_file_name: str
    note: str


@dataclass(frozen=True)
class CapturedArtifact:
    slug: str
    query: str
    path: str
    selected_document: str
    note: str
    locator_label: str
    preview_locator_label: str


@dataclass(frozen=True)
class CaptureManifest:
    case_id: str
    generator_command: str
    output_dir: str
    corpus_dir: str
    input_provenance: dict[str, str]
    artifacts: list[CapturedArtifact]


@dataclass(frozen=True)
class Tc005CapturedArtifact:
    slug: str
    query_id: str
    query: str
    path: str
    selected_document: str
    note: str
    locator_label: str
    preview_locator_label: str


@dataclass(frozen=True)
class Tc005QueryLog:
    query_id: str
    query_type: str
    query: str
    expect_doc: str | None
    lexicon_id: str | None
    expect_empty: bool
    top_k: int
    result_count: int
    total_candidates: int
    trace_id: str
    duration_sec: float
    hit_in_top10: bool
    results: list[dict[str, object]]


@dataclass(frozen=True)
class Tc005FilterLog:
    case_id: str
    query: str
    expect_doc: str
    filters: dict[str, object]
    result_count: int
    total_candidates: int
    trace_id: str
    duration_sec: float
    hit_in_results: bool
    results: list[dict[str, object]]


@dataclass(frozen=True)
class Tc005Manifest:
    case_id: str
    generator_command: str
    output_dir: str
    corpus_dir: str
    query_log_path: str
    input_provenance: dict[str, str]
    artifacts: list[Tc005CapturedArtifact]


@dataclass(frozen=True)
class SearchAcceptanceRuntime:
    search_service: SearchService
    source_root_id: str


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def default_tc018_output_dir() -> Path:
    return _repo_root() / "docs" / "acceptance" / "artifacts" / "s4" / "tc018"


def default_tc005_output_dir() -> Path:
    return _repo_root() / "docs" / "acceptance" / "artifacts" / "s4" / "tc005"


def default_tc018_corpus_dir() -> Path:
    return resolve_s4_tc018_corpus_dir()


def planned_tc018_output_paths(output_dir: Path) -> list[Path]:
    capture_cases = load_s4_acceptance_capture_cases()
    output_paths = [output_dir / f"tc018_{case.slug}.png" for case in capture_cases.tc018]
    output_paths.append(output_dir / "manifest.json")
    return output_paths


def planned_tc005_output_paths(output_dir: Path) -> list[Path]:
    capture_cases = load_s4_acceptance_capture_cases()
    output_paths = [output_dir / f"tc005_{case.slug}.png" for case in capture_cases.tc005]
    output_paths.extend([output_dir / "query_results.json", output_dir / "manifest.json"])
    return output_paths


def _ensure_output_dir(output_dir: Path, *, force: bool) -> None:
    _ensure_expected_outputs(planned_tc018_output_paths(output_dir), force=force, case_id="TC-018")


def _ensure_expected_outputs(output_paths: list[Path], *, force: bool, case_id: str) -> None:
    existing = [path for path in output_paths if path.exists()]
    if existing and not force:
        existing_text = ", ".join(str(path) for path in existing)
        raise FileExistsError(
            f"refusing to overwrite existing {case_id} artifacts without --force: {existing_text}"
        )
    if output_paths:
        output_paths[0].parent.mkdir(parents=True, exist_ok=True)


def _process_events(app: QApplication) -> None:
    for _ in range(3):
        app.processEvents()


def _find_result_item(window: SearchWindow, expected_file_name: str) -> QListWidgetItem:
    from PySide6.QtCore import Qt

    for index in range(window.results_list.count()):
        item = window.results_list.item(index)
        result = item.data(Qt.ItemDataRole.UserRole)
        if result is None:
            continue
        path = getattr(result, "path", "")
        if Path(path).name == expected_file_name:
            return item
    raise LookupError(f"search result not found for {expected_file_name}")


def _capture_window_case(
    *,
    app: QApplication,
    window: SearchWindow,
    output_dir: Path,
    spec: CaptureSpec,
    file_prefix: str,
) -> CapturedArtifact:
    window.query_input.setText(spec.query)
    window.run_search()
    _process_events(app)

    item = _find_result_item(window, spec.expected_file_name)
    window.results_list.setCurrentItem(item)
    _process_events(app)

    location = window.evidence_panel.current_location
    if location is None:
        raise RuntimeError(f"citation location missing for {spec.expected_file_name}")

    window.evidence_panel.locate_button.click()
    _process_events(app)

    preview = window.document_preview_panel.current_preview
    if preview is None:
        raise RuntimeError(f"preview missing for {spec.expected_file_name}")

    output_path = output_dir / f"{file_prefix}_{spec.slug}.png"
    if not window.grab().save(str(output_path)):
        raise OSError(f"failed to save screenshot: {output_path}")

    return CapturedArtifact(
        slug=spec.slug,
        query=spec.query,
        path=str(output_path),
        selected_document=location.path,
        note=spec.note,
        locator_label=window.evidence_panel.locator_label.text(),
        preview_locator_label=window.document_preview_panel.locator_label.text(),
    )


def _build_search_service(
    corpus_dir: Path,
    runtime_dir: Path,
    *,
    source_label: str,
    default_metadata: DocumentMetadata | None = None,
) -> SearchAcceptanceRuntime:
    db_path = runtime_dir / "opendocs.db"
    hnsw_path = runtime_dir / "index" / "hnsw" / "vectors.bin"
    hnsw_path.parent.mkdir(parents=True, exist_ok=True)

    init_db(db_path)
    engine = build_sqlite_engine(db_path)

    source_kwargs: dict[str, object] = {"label": source_label}
    if default_metadata is not None:
        source_kwargs["default_metadata"] = default_metadata
    source = SourceService(engine).add_source(corpus_dir, **source_kwargs)
    IndexService(engine, hnsw_path=hnsw_path).rebuild_index(source.source_root_id)
    return SearchAcceptanceRuntime(
        search_service=SearchService(engine, hnsw_path=hnsw_path),
        source_root_id=source.source_root_id,
    )


def _serialize_tc005_query_log(
    *,
    golden_query: StageGoldenQuery,
    search_service: SearchService,
    top_k: int,
) -> Tc005QueryLog:
    response = search_service.search(golden_query.query, top_k=top_k)
    results = [
        {
            "title": result.title,
            "path": result.path,
            "summary": result.summary,
            "modified_at": result.modified_at.isoformat(),
            "score": result.score,
            "score_breakdown": asdict(result.score_breakdown),
            "citation": asdict(result.citation),
        }
        for result in response.results
    ]
    if golden_query.expect_empty:
        hit_in_top10 = len(response.results) == 0 or response.results[0].score < 0.30
    else:
        assert golden_query.expect_doc is not None
        hit_in_top10 = any(golden_query.expect_doc in result.path for result in response.results[:top_k])
    return Tc005QueryLog(
        query_id=golden_query.query_id,
        query_type=golden_query.query_type,
        query=golden_query.query,
        expect_doc=golden_query.expect_doc,
        lexicon_id=golden_query.lexicon_id,
        expect_empty=golden_query.expect_empty,
        top_k=top_k,
        result_count=len(response.results),
        total_candidates=response.total_candidates,
        trace_id=response.trace_id,
        duration_sec=round(response.duration_sec, 3),
        hit_in_top10=hit_in_top10,
        results=results,
    )


def _serialize_tc005_filter_log(
    *,
    filter_case: StageFilterCase,
    search_service: SearchService,
    corpus_dir: Path,
    primary_source_root_id: str,
) -> Tc005FilterLog:
    filters = filter_case.build_filter(
        corpus_dir=corpus_dir,
        primary_source_root_id=primary_source_root_id,
    )
    response = search_service.search(filter_case.query, filters=filters, top_k=10)
    results = [
        {
            "title": result.title,
            "path": result.path,
            "summary": result.summary,
            "modified_at": result.modified_at.isoformat(),
            "score": result.score,
            "score_breakdown": asdict(result.score_breakdown),
            "citation": asdict(result.citation),
        }
        for result in response.results
    ]
    hit_in_results = any(filter_case.expect_doc in result.path for result in response.results)
    return Tc005FilterLog(
        case_id=filter_case.case_id,
        query=filter_case.query,
        expect_doc=filter_case.expect_doc,
        filters=_serialize_search_filter(filters),
        result_count=len(response.results),
        total_candidates=response.total_candidates,
        trace_id=response.trace_id,
        duration_sec=round(response.duration_sec, 3),
        hit_in_results=hit_in_results,
        results=results,
    )


def _serialize_search_filter(filters: SearchFilter) -> dict[str, object]:
    payload: dict[str, object] = {}
    if filters.directory_prefixes is not None:
        payload["directory_prefixes"] = list(filters.directory_prefixes)
    if filters.source_root_ids is not None:
        payload["source_root_ids"] = list(filters.source_root_ids)
    if filters.categories is not None:
        payload["categories"] = list(filters.categories)
    if filters.tags is not None:
        payload["tags"] = list(filters.tags)
    if filters.file_types is not None:
        payload["file_types"] = list(filters.file_types)
    if filters.sensitivity_levels is not None:
        payload["sensitivity_levels"] = list(filters.sensitivity_levels)
    if filters.time_range is not None:
        payload["time_range"] = {
            "start": filters.time_range[0].isoformat(),
            "end": filters.time_range[1].isoformat(),
        }
    return payload


def _capture_tc005_window_case(
    *,
    app: QApplication,
    window: SearchWindow,
    output_dir: Path,
    spec: CaptureSpec,
    query_id: str,
) -> Tc005CapturedArtifact:
    captured = _capture_window_case(
        app=app,
        window=window,
        output_dir=output_dir,
        spec=spec,
        file_prefix="tc005",
    )
    return Tc005CapturedArtifact(
        slug=spec.slug,
        query_id=query_id,
        query=spec.query,
        path=captured.path,
        selected_document=captured.selected_document,
        note=spec.note,
        locator_label=captured.locator_label,
        preview_locator_label=captured.preview_locator_label,
    )


def _resolve_tc005_capture_spec(
    spec: StageTc005CaptureCase,
    queries_by_id: dict[str, StageGoldenQuery],
) -> CaptureSpec:
    golden_query = queries_by_id[spec.query_id]
    if golden_query.expect_doc is None:
        raise ValueError(f"TC-005 capture spec references non-match query: {spec.query_id}")
    return CaptureSpec(
        slug=spec.slug,
        query=golden_query.query,
        expected_file_name=golden_query.expect_doc,
        note=spec.note,
    )


def capture_s4_tc018_artifacts(
    output_dir: Path,
    *,
    corpus_dir: Path | None = None,
    force: bool = False,
) -> CaptureManifest:
    resolved_output_dir = output_dir.resolve()
    if corpus_dir is None:
        resolved_corpus_dir = resolve_s4_tc018_corpus_dir()
    else:
        resolved_corpus_dir = corpus_dir.resolve()
        if not resolved_corpus_dir.is_dir():
            raise FileNotFoundError(f"TC-018 corpus directory not found: {resolved_corpus_dir}")

    _ensure_output_dir(resolved_output_dir, force=force)

    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    owns_app = app is None
    if app is None:
        app = QApplication([])

    with TemporaryDirectory(prefix="opendocs-tc018-") as runtime:
        capture_cases = load_s4_acceptance_capture_cases()
        runtime_bundle = _build_search_service(
            resolved_corpus_dir,
            Path(runtime),
            source_label="S4 TC-018 artifact capture",
        )
        window = SearchWindow(runtime_bundle.search_service)
        window.resize(1440, 960)
        window.show()
        _process_events(app)

        artifacts = [
            _capture_window_case(
                app=app,
                window=window,
                output_dir=resolved_output_dir,
                spec=spec,
                file_prefix="tc018",
            )
            for spec in (
                CaptureSpec(
                    slug=case.slug,
                    query=case.query,
                    expected_file_name=case.expected_file_name,
                    note=case.note,
                )
                for case in capture_cases.tc018
            )
        ]

        window.close()
        _process_events(app)

    manifest = CaptureManifest(
        case_id="TC-018",
        generator_command=(
            "./.venv/bin/python scripts/capture_s4_tc018_artifacts.py "
            f"--output-dir {resolved_output_dir}"
            + (f" --corpus-dir {resolved_corpus_dir}" if corpus_dir is not None else "")
            + (" --force" if force else "")
        ),
        output_dir=str(resolved_output_dir),
        corpus_dir=str(resolved_corpus_dir),
        input_provenance=build_s4_tc018_input_provenance(),
        artifacts=artifacts,
    )
    manifest_path = resolved_output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(asdict(manifest), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    if owns_app:
        app.quit()

    return manifest


def capture_s4_tc005_artifacts(
    output_dir: Path,
    *,
    corpus_dir: Path | None = None,
    force: bool = False,
) -> Tc005Manifest:
    resolved_output_dir = output_dir.resolve()

    _ensure_expected_outputs(planned_tc005_output_paths(resolved_output_dir), force=force, case_id="TC-005")

    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    owns_app = app is None
    if app is None:
        app = QApplication([])

    with TemporaryDirectory(prefix="opendocs-tc005-") as runtime:
        runtime_dir = Path(runtime)
        capture_cases = load_s4_acceptance_capture_cases()
        if corpus_dir is None:
            resolved_corpus_dir, manifest_corpus_dir = materialize_s4_tc005_acceptance_corpus(
                runtime_dir / "corpus"
            )
        else:
            resolved_corpus_dir = corpus_dir.resolve()
            if not resolved_corpus_dir.is_dir():
                raise FileNotFoundError(f"TC-005 corpus directory not found: {resolved_corpus_dir}")
            manifest_corpus_dir = str(resolved_corpus_dir)

        runtime_bundle = _build_search_service(
            resolved_corpus_dir,
            runtime_dir,
            source_label="S4 TC-005 artifact capture",
            default_metadata=build_s4_search_source_defaults(),
        )
        golden_queries = load_s4_hybrid_search_queries()
        query_logs = [
            _serialize_tc005_query_log(
                golden_query=golden_query,
                search_service=runtime_bundle.search_service,
                top_k=10,
            )
            for golden_query in golden_queries
        ]
        filter_logs = [
            _serialize_tc005_filter_log(
                filter_case=filter_case,
                search_service=runtime_bundle.search_service,
                corpus_dir=resolved_corpus_dir,
                primary_source_root_id=runtime_bundle.source_root_id,
            )
            for filter_case in load_s4_search_filter_cases()
        ]
        queries_by_id = {golden_query.query_id: golden_query for golden_query in golden_queries}

        window = SearchWindow(runtime_bundle.search_service)
        window.resize(1440, 960)
        window.show()
        _process_events(app)

        artifacts = [
            _capture_tc005_window_case(
                app=app,
                window=window,
                output_dir=resolved_output_dir,
                spec=_resolve_tc005_capture_spec(spec, queries_by_id),
                query_id=spec.query_id,
            )
            for spec in capture_cases.tc005
        ]

        window.close()
        _process_events(app)

    query_log_path = resolved_output_dir / "query_results.json"
    query_log_path.write_text(
        json.dumps(
            {
                "case_id": "TC-005",
                "query_count": len(query_logs),
                "filter_case_count": len(filter_logs),
                "logs": [asdict(log) for log in query_logs],
                "filter_logs": [asdict(log) for log in filter_logs],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    manifest = Tc005Manifest(
        case_id="TC-005",
        generator_command=(
            "./.venv/bin/python scripts/capture_s4_tc005_artifacts.py "
            f"--output-dir {resolved_output_dir}"
            + (f" --corpus-dir {resolved_corpus_dir}" if corpus_dir is not None else "")
            + (" --force" if force else "")
        ),
        output_dir=str(resolved_output_dir),
        corpus_dir=manifest_corpus_dir,
        query_log_path=str(query_log_path),
        input_provenance=build_s4_tc005_input_provenance(),
        artifacts=artifacts,
    )
    manifest_path = resolved_output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(asdict(manifest), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    if owns_app:
        app.quit()

    return manifest
