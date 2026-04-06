"""Shared deterministic search environment for S4 verification."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory

from opendocs.domain.document_metadata import DocumentMetadata, merge_document_metadata
from opendocs.parsers import create_default_registry

S4_SEARCH_CORPUS_BUILDER_REF = "src/opendocs/retrieval/stage_search_corpus.py"
S4_SEARCH_SOURCE_DEFAULTS_REF = "src/opendocs/retrieval/stage_search_corpus.py#source_defaults"


@dataclass(frozen=True)
class StageSearchDocumentSpec:
    relative_path: str
    body: str
    declared_category: str | None = None
    declared_tags: tuple[str, ...] = ()
    declared_sensitivity: str | None = None
    modified_at: datetime | None = None

    @property
    def declared_metadata(self) -> DocumentMetadata:
        return DocumentMetadata(
            category=self.declared_category,
            tags=list(self.declared_tags),
            sensitivity=self.declared_sensitivity,
        )

    @property
    def file_type(self) -> str:
        return Path(self.relative_path).suffix.lower().lstrip(".")

    @property
    def relative_directory(self) -> str:
        directory = PurePosixPath(self.relative_path).parent
        return "" if str(directory) == "." else str(directory)

    def render_text(self) -> str:
        if Path(self.relative_path).suffix.lower() != ".md":
            return self.body
        if not (self.declared_category or self.declared_tags or self.declared_sensitivity):
            return self.body

        lines = ["---"]
        if self.declared_category:
            lines.append(f"category: {self.declared_category}")
        if self.declared_tags:
            lines.append("tags:")
            lines.extend(f"  - {tag}" for tag in self.declared_tags)
        if self.declared_sensitivity:
            lines.append(f"sensitivity: {self.declared_sensitivity}")
        lines.append("---")
        lines.append("")
        return "\n".join(lines) + "\n" + self.body


@dataclass(frozen=True)
class StageSearchDocumentProfile:
    relative_path: str
    relative_directory: str
    file_type: str
    metadata: DocumentMetadata
    modified_at: datetime | None


_CORPUS_SPECS: tuple[StageSearchDocumentSpec, ...] = (
    StageSearchDocumentSpec(
        relative_path="zh_project_plan.md",
        declared_category="Project",
        declared_tags=("Roadmap", "Alpha"),
        declared_sensitivity="Sensitive",
        modified_at=datetime(2026, 3, 10, 12, 0, 0),
        body=(
            "# 项目计划书\n\n"
            "本项目的目标是开发一个文档管理工具。\n"
            "项目进度报告将每周更新。\n"
            "第一阶段完成基础架构搭建。\n"
        ),
    ),
    StageSearchDocumentSpec(
        relative_path="zh_meeting_notes.md",
        body=(
            "# 会议纪要\n\n"
            "讨论了项目进度和下一步计划。\n"
            "报告由团队负责人汇总。\n"
            "下次会议定于周四下午两点。\n"
        ),
    ),
    StageSearchDocumentSpec(
        relative_path="mixed_tech_report.md",
        body=(
            "# AI 技术报告\n\n"
            "AI and machine learning 在文档分类中的应用。\n"
            "DB schema 设计需要考虑可扩展性。\n"
            "本报告涵盖自然语言处理的最新进展。\n"
        ),
    ),
    StageSearchDocumentSpec(
        relative_path="en_project_plan.md",
        body=(
            "# Project Plan\n\n"
            "Implementation schedule and milestones for the document management system.\n"
            "Phase 1: Foundation setup and architecture design.\n"
            "Phase 2: Core feature development.\n"
        ),
    ),
    StageSearchDocumentSpec(
        relative_path="en_weekly_report.txt",
        body=(
            "Weekly Status Report\n\n"
            "Completed authentication module review and testing.\n"
            "Next steps include integrating the identity provider.\n"
            "Performance benchmarks show improvement.\n"
        ),
    ),
    StageSearchDocumentSpec(
        relative_path="projects/alpha/alpha_directory_note.md",
        body=(
            "# Alpha Directory Note\n\n"
            "目录过滤专项样本只应该在 alpha 目录命中。\n"
            "This note exists to validate directory-prefix filtering.\n"
        ),
    ),
)

S4_SEARCH_CORPUS_DOCUMENT_PATHS: tuple[str, ...] = tuple(
    spec.relative_path for spec in _CORPUS_SPECS
)
_S4_SEARCH_SOURCE_DEFAULTS = DocumentMetadata(
    category="workspace",
    tags=["shared-source"],
    sensitivity="internal",
)


def list_s4_search_corpus_documents() -> tuple[str, ...]:
    """Return the stage-owned document paths declared by the deterministic S4 corpus."""
    return S4_SEARCH_CORPUS_DOCUMENT_PATHS


def build_s4_search_source_defaults() -> DocumentMetadata:
    """Return the stage-owned source defaults for S4 search environments."""
    return DocumentMetadata.model_validate(_S4_SEARCH_SOURCE_DEFAULTS.model_dump())


def build_s4_search_document_profiles() -> dict[str, StageSearchDocumentProfile]:
    """Return effective per-document search profiles for the stage corpus."""
    return {
        profile.relative_path: _clone_search_document_profile(profile)
        for profile in _load_s4_search_document_profiles()
    }


@lru_cache(maxsize=1)
def _load_s4_search_document_profiles() -> tuple[StageSearchDocumentProfile, ...]:
    """Build the canonical stage profiles once and keep the cache private."""
    source_defaults = build_s4_search_source_defaults()
    registry = create_default_registry()
    profiles: list[StageSearchDocumentProfile] = []
    with TemporaryDirectory(prefix="opendocs-s4-search-corpus-") as temp_dir:
        corpus_dir = materialize_s4_search_corpus(Path(temp_dir))
        for spec in _CORPUS_SPECS:
            file_path = corpus_dir / spec.relative_path
            parsed = registry.parse(file_path)
            if parsed.parse_status == "failed":
                raise ValueError(f"S4 search corpus document failed to parse: {spec.relative_path}")
            profiles.append(
                StageSearchDocumentProfile(
                    relative_path=spec.relative_path,
                    relative_directory=spec.relative_directory,
                    file_type=parsed.file_type,
                    metadata=merge_document_metadata(
                        source_defaults=source_defaults,
                        declared=parsed.metadata,
                    ),
                    modified_at=spec.modified_at,
                )
            )
    return tuple(profiles)


def _clone_search_document_profile(
    profile: StageSearchDocumentProfile,
) -> StageSearchDocumentProfile:
    return StageSearchDocumentProfile(
        relative_path=profile.relative_path,
        relative_directory=profile.relative_directory,
        file_type=profile.file_type,
        metadata=DocumentMetadata.model_validate(profile.metadata.model_dump()),
        modified_at=profile.modified_at,
    )


def materialize_s4_search_corpus(target_dir: Path) -> Path:
    """Materialize the deterministic S4 search corpus into target_dir."""
    target_dir.mkdir(parents=True, exist_ok=True)
    for spec in _CORPUS_SPECS:
        file_path = target_dir / spec.relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(spec.render_text(), encoding="utf-8")
        if spec.modified_at is not None:
            ts = spec.modified_at.timestamp()
            os.utime(file_path, (ts, ts))
    return target_dir
