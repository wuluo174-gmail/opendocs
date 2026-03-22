"""CLI entrypoint for the OpenDocs app."""

from __future__ import annotations

import argparse
import time
from datetime import datetime
from pathlib import Path

from opendocs import __version__
from opendocs.config import load_settings, resolve_app_root
from opendocs.exceptions import ConfigError, SchemaCompatibilityError
from opendocs.utils import get_audit_logger, get_task_logger, init_logging


def _add_source_metadata_arguments(
    parser: argparse.ArgumentParser,
    *,
    allow_clear: bool,
) -> None:
    parser.add_argument(
        "--label",
        default=None,
        help="Optional source label",
    )
    parser.add_argument(
        "--recursive",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Whether to recursively scan the source root",
    )
    parser.add_argument(
        "--category",
        dest="default_category",
        default=None,
        help="Default category for documents under this source root",
    )
    parser.add_argument(
        "--tag",
        dest="default_tags",
        action="append",
        default=None,
        help="Default tags for this source root; repeat or comma-separate values",
    )
    parser.add_argument(
        "--sensitivity",
        dest="default_sensitivity",
        choices=["public", "internal", "sensitive"],
        default=None,
        help="Default sensitivity for this source root",
    )
    if not allow_clear:
        return
    parser.add_argument(
        "--clear-category",
        action="store_true",
        help="Clear the default category",
    )
    parser.add_argument(
        "--clear-tags",
        action="store_true",
        help="Clear the default tags",
    )
    parser.add_argument(
        "--clear-sensitivity",
        action="store_true",
        help="Clear the default sensitivity",
    )


def _add_source_exclude_arguments(
    parser: argparse.ArgumentParser,
    *,
    allow_clear: bool,
) -> None:
    parser.add_argument(
        "--ignore-hidden",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Whether to ignore hidden files and directories",
    )
    parser.add_argument(
        "--exclude-dir",
        dest="exclude_dirs",
        action="append",
        default=None,
        help="Additional directory names to exclude; repeat or comma-separate values",
    )
    parser.add_argument(
        "--exclude-glob",
        dest="exclude_globs",
        action="append",
        default=None,
        help="Additional file globs to exclude; repeat or comma-separate values",
    )
    parser.add_argument(
        "--max-size-bytes",
        type=int,
        default=None,
        help="Exclude files larger than this size",
    )
    if not allow_clear:
        return
    parser.add_argument(
        "--clear-exclude-dirs",
        action="store_true",
        help="Clear excluded directory names before applying --exclude-dir",
    )
    parser.add_argument(
        "--clear-exclude-globs",
        action="store_true",
        help="Clear excluded file globs before applying --exclude-glob",
    )
    parser.add_argument(
        "--clear-max-size-bytes",
        action="store_true",
        help="Clear the file size exclusion limit",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="opendocs",
        description="OpenDocs CLI.",
    )
    parser.add_argument("--version", action="store_true", help="Show OpenDocs version")
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Optional path to settings.toml",
    )

    subparsers = parser.add_subparsers(dest="command")

    # search subcommand
    search_parser = subparsers.add_parser("search", help="Search indexed documents")
    search_parser.add_argument("query", help="Search query text")
    search_parser.add_argument(
        "--top-k", type=int, default=None, help="Number of results (default: 12)"
    )
    search_parser.add_argument(
        "--dir",
        dest="directory_prefixes",
        default=None,
        help="Comma-separated directory prefixes",
    )
    search_parser.add_argument(
        "--source-root-id",
        dest="source_root_ids",
        default=None,
        help="Comma-separated source root ids",
    )
    search_parser.add_argument(
        "--category",
        dest="categories",
        default=None,
        help="Comma-separated categories",
    )
    search_parser.add_argument(
        "--tag",
        dest="tags",
        default=None,
        help="Comma-separated tags",
    )
    search_parser.add_argument(
        "--type",
        dest="file_types",
        default=None,
        help="Comma-separated file types (e.g., md,txt,pdf)",
    )
    search_parser.add_argument(
        "--sensitivity",
        dest="sensitivity_levels",
        default=None,
        help="Comma-separated sensitivity levels",
    )
    search_parser.add_argument(
        "--time-from",
        dest="time_from",
        default=None,
        help="Modified time range start (ISO-like, e.g. 2026-03-01 or 2026-03-01T12:00:00)",
    )
    search_parser.add_argument(
        "--time-to",
        dest="time_to",
        default=None,
        help="Modified time range end (ISO-like, e.g. 2026-03-20 or 2026-03-20T23:59:59)",
    )
    search_parser.add_argument(
        "--open",
        dest="open_n",
        type=int,
        default=None,
        help="Open the Nth result file (1-based)",
    )
    search_parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help="Path to SQLite database",
    )
    search_parser.add_argument(
        "--hnsw",
        type=Path,
        default=None,
        help="Path to HNSW index file",
    )

    status_parser = subparsers.add_parser("status", help="Show index and watcher status")
    status_parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help="Path to SQLite database",
    )
    status_parser.add_argument(
        "--hnsw",
        type=Path,
        default=None,
        help="Path to HNSW index file",
    )

    watch_parser = subparsers.add_parser(
        "watch",
        help="Watch active sources and apply incremental indexing",
    )
    watch_parser.add_argument(
        "--source",
        type=Path,
        default=None,
        help="Optional source directory to add and fully index before watching",
    )
    watch_parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help="Path to SQLite database",
    )
    watch_parser.add_argument(
        "--hnsw",
        type=Path,
        default=None,
        help="Path to HNSW index file",
    )
    watch_parser.add_argument(
        "--debounce",
        type=float,
        default=1.0,
        help="File watcher debounce window in seconds",
    )
    _add_source_metadata_arguments(watch_parser, allow_clear=False)
    _add_source_exclude_arguments(watch_parser, allow_clear=False)

    source_parser = subparsers.add_parser("source", help="Manage source roots")
    source_subparsers = source_parser.add_subparsers(dest="source_command")

    source_add_parser = source_subparsers.add_parser("add", help="Add or update a source root")
    source_add_parser.add_argument("path", type=Path, help="Source root directory path")
    source_add_parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help="Path to SQLite database",
    )
    source_add_parser.add_argument(
        "--hnsw",
        type=Path,
        default=None,
        help="Path to HNSW index file",
    )
    _add_source_metadata_arguments(source_add_parser, allow_clear=False)
    _add_source_exclude_arguments(source_add_parser, allow_clear=False)

    source_update_parser = source_subparsers.add_parser(
        "update",
        help="Update a source root configuration",
    )
    source_update_parser.add_argument("source_root_id", help="Source root id")
    source_update_parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help="Path to SQLite database",
    )
    source_update_parser.add_argument(
        "--hnsw",
        type=Path,
        default=None,
        help="Path to HNSW index file",
    )
    _add_source_metadata_arguments(source_update_parser, allow_clear=True)
    _add_source_exclude_arguments(source_update_parser, allow_clear=True)

    source_list_parser = source_subparsers.add_parser("list", help="List configured source roots")
    source_list_parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help="Path to SQLite database",
    )
    source_list_parser.add_argument(
        "--hnsw",
        type=Path,
        default=None,
        help="Path to HNSW index file",
    )

    return parser


def _ensure_runtime_dirs(app_root: Path) -> None:
    for subdir in [
        Path("config"),
        Path("logs"),
        Path("data"),
        Path("index") / "hnsw",
        Path("index") / "cache",
        Path("rollback"),
        Path("output"),
        Path("temp"),
    ]:
        (app_root / subdir).mkdir(parents=True, exist_ok=True)


def _resolve_runtime(args: argparse.Namespace) -> tuple[object, Path, Path, Path]:
    settings = load_settings(args.config)
    app_root = resolve_app_root(args.config)
    _ensure_runtime_dirs(app_root)
    init_logging(app_root / "logs")
    db_path = getattr(args, "db", None) or (app_root / "data" / "opendocs.db")
    hnsw_path = getattr(args, "hnsw", None) or (app_root / "index" / "hnsw" / "chunks.hnsw")
    return settings, app_root, db_path, hnsw_path


def _parse_csv_option(value: str | None) -> list[str] | None:
    if value is None:
        return None
    items = [item.strip() for item in value.split(",") if item.strip()]
    return items or None


def _parse_multi_value_option(values: list[str] | None) -> list[str] | None:
    if not values:
        return None
    items: list[str] = []
    for value in values:
        items.extend(item.strip() for item in value.split(",") if item.strip())
    return items or None


def _parse_time_option(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value)


def _build_search_filter(args: argparse.Namespace):
    from opendocs.retrieval.filters import SearchFilter

    time_from = _parse_time_option(getattr(args, "time_from", None))
    time_to = _parse_time_option(getattr(args, "time_to", None))
    time_range = None
    if time_from is not None or time_to is not None:
        if time_from is None or time_to is None:
            raise ValueError("--time-from and --time-to must be provided together")
        time_range = (time_from, time_to)

    return SearchFilter(
        directory_prefixes=_parse_csv_option(getattr(args, "directory_prefixes", None)),
        source_root_ids=_parse_csv_option(getattr(args, "source_root_ids", None)),
        categories=_parse_csv_option(getattr(args, "categories", None)),
        tags=_parse_csv_option(getattr(args, "tags", None)),
        file_types=_parse_csv_option(getattr(args, "file_types", None)),
        sensitivity_levels=_parse_csv_option(getattr(args, "sensitivity_levels", None)),
        time_range=time_range,
    )


def _build_source_default_metadata(
    args: argparse.Namespace,
    *,
    existing_source=None,
):
    from opendocs.domain.document_metadata import DocumentMetadata

    has_category_update = getattr(args, "default_category", None) is not None or getattr(
        args, "clear_category", False
    )
    has_tag_update = getattr(args, "default_tags", None) is not None or getattr(
        args, "clear_tags", False
    )
    has_sensitivity_update = getattr(args, "default_sensitivity", None) is not None or getattr(
        args, "clear_sensitivity", False
    )
    if not any((has_category_update, has_tag_update, has_sensitivity_update)):
        return None

    category = None
    tags: list[str] = []
    sensitivity = None
    if existing_source is not None:
        category = existing_source.default_category
        tags = list(existing_source.default_tags_json or [])
        sensitivity = existing_source.default_sensitivity

    if has_category_update:
        category = (
            None
            if getattr(args, "clear_category", False)
            else getattr(args, "default_category", None)
        )
    if has_tag_update:
        tags = [] if getattr(args, "clear_tags", False) else (_parse_multi_value_option(args.default_tags) or [])
    if has_sensitivity_update:
        sensitivity = (
            None
            if getattr(args, "clear_sensitivity", False)
            else getattr(args, "default_sensitivity", None)
        )

    return DocumentMetadata(
        category=category,
        tags=tags,
        sensitivity=sensitivity,
    )


def _merge_preserving_order(current: list[str], additions: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for value in [*current, *additions]:
        normalized = value.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        merged.append(normalized)
    return merged


def _build_source_exclude_rules(
    args: argparse.Namespace,
    *,
    existing_source=None,
):
    from opendocs.indexing.scanner import ExcludeRules

    has_ignore_hidden_update = getattr(args, "ignore_hidden", None) is not None
    has_dir_update = getattr(args, "exclude_dirs", None) is not None or getattr(
        args,
        "clear_exclude_dirs",
        False,
    )
    has_glob_update = getattr(args, "exclude_globs", None) is not None or getattr(
        args,
        "clear_exclude_globs",
        False,
    )
    has_max_size_update = getattr(args, "max_size_bytes", None) is not None or getattr(
        args,
        "clear_max_size_bytes",
        False,
    )
    if not any(
        (
            has_ignore_hidden_update,
            has_dir_update,
            has_glob_update,
            has_max_size_update,
        )
    ):
        return None

    current = ExcludeRules()
    if existing_source is not None:
        current = ExcludeRules.model_validate(existing_source.exclude_rules_json or {})

    ignore_hidden = current.ignore_hidden
    exclude_dirs = list(current.exclude_dirs)
    exclude_globs = list(current.exclude_globs)
    max_size_bytes = current.max_size_bytes

    if has_ignore_hidden_update:
        ignore_hidden = args.ignore_hidden
    if has_dir_update:
        additions = _parse_multi_value_option(args.exclude_dirs) or []
        base_dirs = [] if getattr(args, "clear_exclude_dirs", False) else exclude_dirs
        exclude_dirs = _merge_preserving_order(base_dirs, additions)
    if has_glob_update:
        additions = _parse_multi_value_option(args.exclude_globs) or []
        base_globs = [] if getattr(args, "clear_exclude_globs", False) else exclude_globs
        exclude_globs = _merge_preserving_order(base_globs, additions)
    if has_max_size_update:
        max_size_bytes = (
            None if getattr(args, "clear_max_size_bytes", False) else args.max_size_bytes
        )

    return ExcludeRules(
        ignore_hidden=ignore_hidden,
        exclude_dirs=exclude_dirs,
        exclude_globs=exclude_globs,
        max_size_bytes=max_size_bytes,
    )


def _build_source_service_kwargs(
    args: argparse.Namespace,
    *,
    existing_source=None,
) -> dict[str, object]:
    kwargs: dict[str, object] = {}
    if getattr(args, "label", None) is not None:
        kwargs["label"] = args.label
    if getattr(args, "recursive", None) is not None:
        kwargs["recursive"] = args.recursive

    default_metadata = _build_source_default_metadata(args, existing_source=existing_source)
    if default_metadata is not None:
        kwargs["default_metadata"] = default_metadata
    exclude_rules = _build_source_exclude_rules(args, existing_source=existing_source)
    if exclude_rules is not None:
        kwargs["exclude_rules"] = exclude_rules
    return kwargs


def _print_source(source) -> None:
    from opendocs.indexing.scanner import ExcludeRules

    rules = ExcludeRules.model_validate(source.exclude_rules_json or {})
    default_tags = ",".join(source.default_tags_json or [])
    print(f"source_root_id={source.source_root_id}")
    print(f"path={source.path}")
    print(f"label={source.label or ''}")
    print(f"recursive={source.recursive}")
    print(f"exclude_ignore_hidden={rules.ignore_hidden}")
    print(f"exclude_dirs={','.join(rules.exclude_dirs)}")
    print(f"exclude_globs={','.join(rules.exclude_globs)}")
    print(
        "exclude_max_size_bytes="
        f"{'' if rules.max_size_bytes is None else rules.max_size_bytes}"
    )
    print(f"default_category={source.default_category or ''}")
    print(f"default_tags={default_tags}")
    print(f"default_sensitivity={source.default_sensitivity or ''}")


def _find_source_by_path(service, path: Path):
    resolved = path.expanduser().resolve()
    for source in service.list_sources():
        if Path(source.path).resolve() == resolved:
            return source
    return None


def _run_search(args: argparse.Namespace) -> int:
    """Execute the search subcommand."""
    from opendocs.app.search_service import SearchService
    from opendocs.storage.db import build_sqlite_engine, init_db

    settings, _, db_path, hnsw_path = _resolve_runtime(args)

    if not db_path.exists():
        print(f"Database not found: {db_path}")
        return 1

    try:
        init_db(db_path)
        engine = build_sqlite_engine(db_path)
    except SchemaCompatibilityError as exc:
        print(f"schema error: {exc}")
        return 2
    svc = SearchService(engine, hnsw_path=hnsw_path, settings=settings.retrieval)

    try:
        search_filter = _build_search_filter(args)
        response = svc.search(args.query, filters=search_filter, top_k=args.top_k)
    except ValueError as exc:
        print(f"Search error: {exc}")
        return 1

    if not response.results:
        print("No results found.")
        return 0

    for i, result in enumerate(response.results, 1):
        cit = result.citation
        loc_parts = []
        if cit.page_no is not None:
            loc_parts.append(f"p.{cit.page_no}")
        if cit.paragraph_range is not None:
            loc_parts.append(f"para.{cit.paragraph_range}")
        loc_parts.append(f"chars {cit.char_range}")
        location = ", ".join(loc_parts)

        bd = result.score_breakdown
        print(f"\n[{i}] {result.title}")
        print(f"    Path: {result.path}")
        print(f"    Summary: {result.summary}")
        print(f"    Modified: {result.modified_at}")
        print(
            f"    Score: {result.score:.3f} "
            f"(lex={bd.lexical_normalized:.2f}, "
            f"dense={bd.dense_normalized:.2f}, "
            f"fresh={bd.freshness_boost:.2f})"
        )
        print(f"    Citation: {location}")
        print(f'    Preview: "{cit.quote_preview}"')

    print(f"\n--- {len(response.results)} results, {response.duration_sec:.3f}s ---")

    # --open N
    if args.open_n is not None:
        idx = args.open_n - 1
        if 0 <= idx < len(response.results):
            selected = response.results[idx]
            if svc.open_evidence(selected.doc_id, selected.chunk_id):
                print(f"Opened: {selected.path}")
            else:
                print(f"Cannot open: {selected.path}")
        else:
            print(f"Invalid result number: {args.open_n}")

    return 0


def _run_status(args: argparse.Namespace) -> int:
    from opendocs.app.index_service import IndexService
    from opendocs.storage.db import build_sqlite_engine, init_db

    settings, _, db_path, hnsw_path = _resolve_runtime(args)

    try:
        init_db(db_path)
        engine = build_sqlite_engine(db_path)
    except SchemaCompatibilityError as exc:
        print(f"schema error: {exc}")
        return 2

    status = IndexService(
        engine,
        hnsw_path=hnsw_path,
        watch_changes=settings.index.watch_changes,
    ).get_index_status()

    print(f"watch_changes={status.watch_changes_enabled}")
    print(f"watcher_running={status.watcher_running}")
    print(f"active_sources={status.active_source_count}")
    print(f"watched_sources={status.watched_source_count}")
    print(f"documents={status.active_document_count}/{status.total_document_count}")
    print(f"chunks={status.total_chunk_count}")
    print(f"hnsw_status={status.hnsw_status}")
    if status.last_scan_status is not None:
        print(f"last_scan_status={status.last_scan_status}")
    if status.last_scan_finished_at is not None:
        print(f"last_scan_finished_at={status.last_scan_finished_at}")
    if status.watched_paths:
        for watched_path in status.watched_paths:
            print(f"watched_path={watched_path}")

    return 0


def _run_watch(args: argparse.Namespace) -> int:
    from opendocs.app.index_service import IndexService
    from opendocs.app.source_service import SourceService
    from opendocs.storage.db import build_sqlite_engine, init_db

    settings, _, db_path, hnsw_path = _resolve_runtime(args)

    try:
        init_db(db_path)
        engine = build_sqlite_engine(db_path)
    except SchemaCompatibilityError as exc:
        print(f"schema error: {exc}")
        return 2

    source_service = SourceService(engine, hnsw_path=hnsw_path)
    index_service = IndexService(
        engine,
        hnsw_path=hnsw_path,
        watch_changes=settings.index.watch_changes,
    )

    if args.source is not None:
        existing_source = _find_source_by_path(source_service, args.source)
        source = source_service.add_source(
            args.source,
            reindex_on_change=False,
            **_build_source_service_kwargs(args, existing_source=existing_source),
        )
        result = index_service.full_index_source(source.source_root_id)
        print(
            "initial_index="
            f"{result.success_count} success, "
            f"{result.partial_count} partial, "
            f"{result.failed_count} failed, "
            f"{result.skipped_count} skipped"
        )

    status = index_service.start_watching_active_sources(debounce_seconds=args.debounce)
    if not status.watch_changes_enabled:
        print("Watcher disabled by config: index.watch_changes=false")
        return 0
    if not status.watcher_running:
        print("Watcher not started: no active sources available.")
        return 1

    print(f"Watching {status.watched_source_count} source(s). Press Ctrl+C to stop.")
    for watched_path in status.watched_paths:
        print(f"watching={watched_path}")

    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        index_service.stop_watching()
        print("Watcher stopped.")
        return 0


def _run_source(args: argparse.Namespace) -> int:
    from opendocs.app.source_service import SourceService
    from opendocs.exceptions import SourceNotFoundError
    from opendocs.storage.db import build_sqlite_engine, init_db

    _, _, db_path, hnsw_path = _resolve_runtime(args)

    try:
        init_db(db_path)
        engine = build_sqlite_engine(db_path)
    except SchemaCompatibilityError as exc:
        print(f"schema error: {exc}")
        return 2

    service = SourceService(engine, hnsw_path=hnsw_path)

    try:
        if args.source_command == "list":
            sources = service.list_sources()
            if not sources:
                print("No sources configured.")
                return 0
            for idx, source in enumerate(sources):
                if idx > 0:
                    print("")
                _print_source(source)
            return 0

        if args.source_command == "add":
            existing_source = _find_source_by_path(service, args.path)
            source = service.add_source(
                args.path,
                **_build_source_service_kwargs(args, existing_source=existing_source),
            )
            print("source_status=ready")
            _print_source(source)
            return 0

        if args.source_command == "update":
            existing_source = service.get_source(args.source_root_id)
            if existing_source is None:
                print(f"source error: source root not found: {args.source_root_id}")
                return 1
            source = service.update_source(
                args.source_root_id,
                **_build_source_service_kwargs(args, existing_source=existing_source),
            )
            print("source_status=updated")
            _print_source(source)
            return 0
    except (SourceNotFoundError, ValueError) as exc:
        print(f"source error: {exc}")
        return 1

    print("source error: missing subcommand")
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.version:
        print(__version__)
        return 0

    try:
        if args.command == "search":
            return _run_search(args)
        if args.command == "status":
            return _run_status(args)
        if args.command == "watch":
            return _run_watch(args)
        if args.command == "source":
            return _run_source(args)

        # Default: baseline startup
        settings = load_settings(args.config)
    except ConfigError as exc:
        print(f"config error: {exc}")
        return 2

    app_root = resolve_app_root(args.config)
    _ensure_runtime_dirs(app_root)

    log_root = app_root / "logs"
    logger = init_logging(log_root)
    audit_logger = get_audit_logger()
    task_logger = get_task_logger()
    logger.info("OpenDocs CLI started")
    audit_logger.info("OpenDocs audit logger started")
    task_logger.info("OpenDocs task logger started")
    print("OpenDocs baseline started.")
    print(f"language={settings.app.language} local_only={settings.app.local_only}")
    return 0
