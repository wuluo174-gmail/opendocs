"""Evidence locator — locate and open source files for citations."""

from __future__ import annotations

import platform
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from sqlalchemy.orm import Session

from opendocs.domain import CharRange, ParagraphRange
from opendocs.parsers import ParserRegistry, create_default_registry
from opendocs.storage.repositories import ChunkRepository, DocumentRepository


@dataclass(frozen=True)
class EvidenceLocation:
    path: str
    page_no: int | None
    paragraph_range: str | None
    char_range: str  # best-effort (ADR-0010)
    quote_preview: str
    can_open: bool
    external_jump_supported: bool


@dataclass(frozen=True)
class EvidencePreview:
    path: str
    page_no: int | None
    paragraph_range: str | None
    char_range: str
    preview_text: str
    highlight_start: int
    highlight_end: int
    quote_preview: str


@dataclass(frozen=True)
class ExternalActionResult:
    """Structured outcome for best-effort external open/reveal side effects."""

    action: Literal["open", "reveal"]
    status: Literal[
        "launched",
        "missing_target",
        "unsupported_platform",
        "launch_failed",
        "unresolved_evidence",
    ]
    target_path: str | None
    external_target: str | None
    locator_hint_applied: bool
    message: str
    error: str | None = None

    @property
    def launched(self) -> bool:
        return self.status == "launched"


@dataclass(frozen=True)
class _ResolvedEvidenceTarget:
    absolute_path: str
    display_path: str
    page_no: int | None
    paragraph_range: str | None
    char_range: str
    quote_preview: str
    can_open: bool
    external_jump_supported: bool


@dataclass(frozen=True)
class _ExternalOpenPlan:
    target: str
    locator_hint_applied: bool


class EvidenceLocator:
    """Locate evidence for a given chunk and optionally open the file."""

    def __init__(self, registry: ParserRegistry | None = None) -> None:
        self._registry = registry or create_default_registry()

    def locate(self, session: Session, doc_id: str, chunk_id: str) -> EvidenceLocation | None:
        """Resolve location for a specific chunk."""
        target = self._resolve_target(session, doc_id, chunk_id)
        if target is None:
            return None

        return EvidenceLocation(
            path=target.display_path,
            page_no=target.page_no,
            paragraph_range=target.paragraph_range,
            char_range=target.char_range,
            quote_preview=target.quote_preview,
            can_open=target.can_open,
            external_jump_supported=target.external_jump_supported,
        )

    def build_preview(
        self,
        session: Session,
        doc_id: str,
        chunk_id: str,
        *,
        surrounding_paragraphs: int = 1,
    ) -> EvidencePreview | None:
        """Build an in-app, local-first preview anchored to the citation."""
        target = self._resolve_target(session, doc_id, chunk_id)
        if target is None:
            return None

        parsed = self._registry.parse(Path(target.absolute_path))
        if parsed.parse_status == "failed" or not parsed.raw_text:
            return EvidencePreview(
                path=target.display_path,
                page_no=target.page_no,
                paragraph_range=target.paragraph_range,
                char_range=target.char_range,
                preview_text=target.quote_preview,
                highlight_start=0,
                highlight_end=len(target.quote_preview),
                quote_preview=target.quote_preview,
            )

        char_locator = CharRange.parse(target.char_range)
        slice_start, slice_end = self._resolve_preview_slice(
            parsed,
            char_locator,
            page_no=target.page_no,
            surrounding_paragraphs=surrounding_paragraphs,
        )
        preview_text = parsed.raw_text[slice_start:slice_end]

        if not preview_text:
            preview_text = target.quote_preview
            highlight_start = 0
            highlight_end = len(target.quote_preview)
        else:
            clamped_start = min(max(char_locator.start, slice_start), slice_end)
            clamped_end = min(max(char_locator.end, clamped_start), slice_end)
            highlight_start = clamped_start - slice_start
            highlight_end = clamped_end - slice_start

            if highlight_start == highlight_end:
                fallback_index = preview_text.find(target.quote_preview.rstrip("."))
                if fallback_index >= 0:
                    highlight_start = fallback_index
                    highlight_end = fallback_index + len(target.quote_preview.rstrip("."))

        return EvidencePreview(
            path=target.display_path,
            page_no=target.page_no,
            paragraph_range=target.paragraph_range,
            char_range=target.char_range,
            preview_text=preview_text,
            highlight_start=highlight_start,
            highlight_end=highlight_end,
            quote_preview=target.quote_preview,
        )

    def resolve_open_target(
        self,
        session: Session,
        doc_id: str,
        chunk_id: str,
    ) -> tuple[str, int | None, str | None, str] | None:
        """Resolve the internal file-open target for a citation."""
        target = self._resolve_target(session, doc_id, chunk_id)
        if target is None:
            return None
        return (
            target.absolute_path,
            target.page_no,
            target.paragraph_range,
            target.char_range,
        )

    @staticmethod
    def unresolved_evidence_result(action: Literal["open", "reveal"]) -> ExternalActionResult:
        return ExternalActionResult(
            action=action,
            status="unresolved_evidence",
            target_path=None,
            external_target=None,
            locator_hint_applied=False,
            message="evidence target could not be resolved",
        )

    def _resolve_target(
        self,
        session: Session,
        doc_id: str,
        chunk_id: str,
    ) -> _ResolvedEvidenceTarget | None:
        doc_repo = DocumentRepository(session)
        chunk_repo = ChunkRepository(session)
        doc = doc_repo.get_by_id(doc_id)
        chunk = chunk_repo.get_by_id(chunk_id)
        if doc is None or chunk is None or chunk.doc_id != doc_id:
            return None

        para_locator = ParagraphRange.from_storage(chunk.paragraph_start, chunk.paragraph_end)
        char_locator = CharRange(start=chunk.char_start, end=chunk.char_end)
        quote = chunk.text[:120].replace("\n", " ").strip()
        if len(chunk.text) > 120:
            quote += "..."

        return _ResolvedEvidenceTarget(
            absolute_path=doc.path,
            display_path=doc.display_path,
            page_no=chunk.page_no,
            paragraph_range=(para_locator.to_display_range() if para_locator is not None else None),
            char_range=char_locator.to_display_range(),
            quote_preview=quote,
            can_open=Path(doc.path).exists(),
            external_jump_supported=self._supports_precise_external_jump(
                doc.path,
                page_no=chunk.page_no,
            ),
        )

    @staticmethod
    def _supports_precise_external_jump(path: str, *, page_no: int | None) -> bool:
        return Path(path).suffix.lower() == ".pdf" and page_no is not None

    @staticmethod
    def _resolve_preview_slice(
        parsed,
        char_locator: CharRange,
        *,
        page_no: int | None,
        surrounding_paragraphs: int,
    ) -> tuple[int, int]:
        paragraphs = parsed.paragraphs
        if not paragraphs:
            return EvidenceLocator._fallback_char_slice(parsed.raw_text, char_locator)

        overlapping = [
            idx
            for idx, para in enumerate(paragraphs)
            if para.end_char > char_locator.start and para.start_char < char_locator.end
        ]
        if not overlapping:
            overlapping = [
                EvidenceLocator._find_nearest_paragraph_index(paragraphs, char_locator.start)
            ]

        start_idx = overlapping[0]
        end_idx = overlapping[-1]

        for _ in range(surrounding_paragraphs):
            if start_idx > 0 and EvidenceLocator._same_preview_scope(
                paragraphs[start_idx - 1],
                page_no=page_no,
            ):
                start_idx -= 1
            if end_idx + 1 < len(paragraphs) and EvidenceLocator._same_preview_scope(
                paragraphs[end_idx + 1],
                page_no=page_no,
            ):
                end_idx += 1

        return paragraphs[start_idx].start_char, paragraphs[end_idx].end_char

    @staticmethod
    def _fallback_char_slice(raw_text: str, char_locator: CharRange) -> tuple[int, int]:
        context_chars = 160
        start = max(0, char_locator.start - context_chars)
        end = min(len(raw_text), char_locator.end + context_chars)
        return start, end

    @staticmethod
    def _find_nearest_paragraph_index(paragraphs, char_start: int) -> int:
        for idx, para in enumerate(paragraphs):
            if para.start_char <= char_start < para.end_char:
                return idx
            if char_start < para.start_char:
                return idx
        return len(paragraphs) - 1

    @staticmethod
    def _same_preview_scope(para, *, page_no: int | None) -> bool:
        if page_no is None:
            return True
        return para.page_no == page_no

    @staticmethod
    def _build_open_target(
        path: Path,
        *,
        page_no: int | None = None,
        paragraph_range: str | None = None,
        char_range: str | None = None,
    ) -> _ExternalOpenPlan:
        resolved = path.resolve()
        if page_no is not None and path.suffix.lower() == ".pdf":
            return _ExternalOpenPlan(
                target=f"{resolved.as_uri()}#page={page_no}",
                locator_hint_applied=True,
            )
        return _ExternalOpenPlan(
            target=str(resolved),
            locator_hint_applied=False,
        )

    @staticmethod
    def open_file(
        path: str,
        *,
        page_no: int | None = None,
        paragraph_range: str | None = None,
        char_range: str | None = None,
    ) -> ExternalActionResult:
        """Open a file with the platform default application.

        Locator hints are threaded through so callers do not lose citation
        context at the UI/service boundary. Only hints backed by a concrete
        external-app protocol are forwarded; paragraph/char anchors remain an
        in-app preview concern until we have a true editor adapter.
        """
        p = Path(path)
        if not p.exists():
            return ExternalActionResult(
                action="open",
                status="missing_target",
                target_path=str(p),
                external_target=None,
                locator_hint_applied=False,
                message=f"file not found: {p}",
            )
        plan = EvidenceLocator._build_open_target(
            p,
            page_no=page_no,
            paragraph_range=paragraph_range,
            char_range=char_range,
        )
        locator_hint_applied = plan.locator_hint_applied
        system = platform.system().lower()
        try:
            if system == "darwin":
                subprocess.Popen(["open", plan.target])  # noqa: S603
            elif system == "linux":
                subprocess.Popen(["xdg-open", plan.target])  # noqa: S603
            elif system == "windows":
                subprocess.Popen(["start", "", plan.target], shell=True)  # noqa: S603 S602
            else:
                return ExternalActionResult(
                    action="open",
                    status="unsupported_platform",
                    target_path=str(p.resolve()),
                    external_target=plan.target,
                    locator_hint_applied=locator_hint_applied,
                    message=f"unsupported platform opener: {system}",
                )
            return ExternalActionResult(
                action="open",
                status="launched",
                target_path=str(p.resolve()),
                external_target=plan.target,
                locator_hint_applied=locator_hint_applied,
                message="external open request launched",
            )
        except OSError as exc:
            return ExternalActionResult(
                action="open",
                status="launch_failed",
                target_path=str(p.resolve()),
                external_target=plan.target,
                locator_hint_applied=locator_hint_applied,
                message=f"failed to launch external opener: {exc}",
                error=str(exc),
            )

    @staticmethod
    def reveal_in_file_manager(path: str) -> ExternalActionResult:
        """Reveal a document in the platform file manager."""
        p = Path(path)
        if not p.exists():
            return ExternalActionResult(
                action="reveal",
                status="missing_target",
                target_path=str(p),
                external_target=None,
                locator_hint_applied=False,
                message=f"file not found: {p}",
            )

        resolved = str(p.resolve())
        system = platform.system().lower()
        try:
            if system == "darwin":
                subprocess.Popen(["open", "-R", resolved])  # noqa: S603
            elif system == "linux":
                subprocess.Popen(["xdg-open", str(p.resolve().parent)])  # noqa: S603
            elif system == "windows":
                subprocess.Popen(["explorer", f"/select,{resolved}"])  # noqa: S603
            else:
                return ExternalActionResult(
                    action="reveal",
                    status="unsupported_platform",
                    target_path=resolved,
                    external_target=None,
                    locator_hint_applied=False,
                    message=f"unsupported platform file manager: {system}",
                )
            return ExternalActionResult(
                action="reveal",
                status="launched",
                target_path=resolved,
                external_target=None,
                locator_hint_applied=False,
                message="external reveal request launched",
            )
        except OSError as exc:
            return ExternalActionResult(
                action="reveal",
                status="launch_failed",
                target_path=resolved,
                external_target=None,
                locator_hint_applied=False,
                message=f"failed to launch file manager: {exc}",
                error=str(exc),
            )
