"""Standalone fixtures for S5 summary integration tests."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.engine import Engine

from opendocs.app.runtime import OpenDocsRuntime
from opendocs.app.qa_service import QAService
from opendocs.app.source_service import SourceService
from opendocs.domain.models import DocumentModel
from opendocs.storage.db import build_sqlite_engine, init_db, session_scope


def _write_doc(path: Path, body: str, *, modified_at: datetime) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    ts = modified_at.timestamp()
    os.utime(path, (ts, ts))


def _materialize_s5_corpus(target_dir: Path) -> Path:
    docs = {
        "projects/atlas/owner_brief.md": (
            datetime(2026, 3, 11, 9, 0, 0),
            "# Atlas 项目概览\n\n"
            "项目名称：Atlas\n"
            "Atlas 项目负责人：王敏\n"
            "项目阶段：试点准备\n"
            "决策：先完成导入器。\n"
            "风险：供应商接口仍未稳定。\n"
            "待办：整理测试清单。\n",
        ),
        "projects/atlas/weekly_01.md": (
            datetime(2026, 3, 12, 10, 0, 0),
            "# Atlas 周报 01\n\n"
            "项目名称：Atlas\n"
            "Atlas 项目负责人：王敏\n"
            "决策：四月第一周开始内部试用。\n"
            "风险：历史数据映射规则仍需确认。\n"
            "待办：补齐迁移脚本回归测试。\n",
        ),
        "projects/atlas/weekly_02.md": (
            datetime(2026, 3, 19, 10, 0, 0),
            "# Atlas 周报 02\n\n"
            "项目名称：Atlas\n"
            "决策：上线前先冻结字段变更。\n"
            "风险：导入性能在大文件场景下仍有抖动。\n"
            "待办：补充性能压测样本。\n",
        ),
        "projects/atlas/meeting_01.md": (
            datetime(2026, 3, 13, 14, 0, 0),
            "# Atlas 会议纪要 01\n\n"
            "决策：采用双阶段导出流程。\n"
            "风险：引用校验器误判会拖慢交付。\n"
            "待办：补齐冲突案例测试。\n",
        ),
        "projects/atlas/meeting_02.md": (
            datetime(2026, 3, 20, 14, 0, 0),
            "# Atlas 会议纪要 02\n\n"
            "决策：界面默认展示引用面板。\n"
            "风险：旧版本周报可能与新计划冲突。\n"
            "待办：梳理需要人工复核的条目。\n",
        ),
        "projects/atlas/meeting_03.md": (
            datetime(2026, 3, 27, 14, 0, 0),
            "# Atlas 会议纪要 03\n\n"
            "决策：摘要导出统一使用 Markdown。\n"
            "风险：跨文档汇总时噪音片段过多。\n"
            "待办：限制每个文档进入摘要的片段数。\n",
        ),
        "projects/atlas/meeting_04.md": (
            datetime(2026, 4, 3, 14, 0, 0),
            "# Atlas 会议纪要 04\n\n"
            "决策：冲突回答不再强行归并单一结论。\n"
            "风险：版本标记不清会增加人工确认成本。\n"
            "待办：为版本文档补齐统一命名规则。\n",
        ),
        "projects/atlas/monthly_01.md": (
            datetime(2026, 4, 5, 9, 30, 0),
            "# Atlas 月报\n\n"
            "决策：四月只开放给项目内团队试用。\n"
            "风险：供应商接口窗口可能再次变更。\n"
            "待办：准备试点培训材料。\n",
        ),
        "projects/atlas/release_plan_v1.md": (
            datetime(2026, 3, 15, 12, 0, 0),
            "# Atlas 发布计划 V1\n\n"
            "项目名称：Atlas\n"
            "Atlas 发布时间：2026-03-15\n"
            "说明：该版本面向第一批内部用户。\n",
        ),
        "projects/atlas/release_plan_v2.md": (
            datetime(2026, 4, 1, 12, 0, 0),
            "# Atlas 发布计划 V2\n\n"
            "项目名称：Atlas\n"
            "Atlas 发布时间：2026-04-01\n"
            "说明：由于供应商接口延期，发布时间后移。\n",
        ),
        "projects/aurora/owner_story.md": (
            datetime(2026, 4, 2, 9, 0, 0),
            "# Aurora 简报\n\nAurora 项目的负责人是赵宁。团队预计五月开始试运行。\n",
        ),
        "projects/aurora/meeting_story.md": (
            datetime(2026, 4, 2, 14, 0, 0),
            "# Aurora 会议纪要\n\n"
            "本次会议决定五月开始试点。当前主要风险是外部接口仍不稳定。"
            "团队下周需要补齐回归测试清单。\n",
        ),
    }
    target_dir.mkdir(parents=True, exist_ok=True)
    for relative_path, (modified_at, body) in docs.items():
        _write_doc(target_dir / relative_path, body, modified_at=modified_at)
    return target_dir


@pytest.fixture()
def qa_corpus(tmp_path: Path) -> Path:
    return _materialize_s5_corpus(tmp_path / "corpus")


@pytest.fixture()
def qa_db(tmp_path: Path) -> Path:
    return tmp_path / "summary_test.db"


@pytest.fixture()
def summary_runtime(qa_db: Path, tmp_path: Path) -> OpenDocsRuntime:
    init_db(qa_db)
    engine = build_sqlite_engine(qa_db)
    hnsw_path = tmp_path / "hnsw" / "summary_test.hnsw"
    hnsw_path.parent.mkdir(parents=True, exist_ok=True)
    runtime = OpenDocsRuntime(engine, hnsw_path=hnsw_path)
    try:
        yield runtime
    finally:
        runtime.close()


@pytest.fixture()
def indexed_qa_env(
    qa_corpus: Path,
    qa_db: Path,
    summary_runtime: OpenDocsRuntime,
) -> tuple[Engine, Path, Path]:
    engine = summary_runtime.engine
    hnsw_path = summary_runtime.hnsw_path
    assert hnsw_path is not None

    source = SourceService(engine, runtime=summary_runtime).add_source(qa_corpus)
    summary_runtime.build_index_service().full_index_source(source.source_root_id)
    return engine, qa_db, hnsw_path


@pytest.fixture()
def qa_service(
    indexed_qa_env: tuple[Engine, Path, Path],
    summary_runtime: OpenDocsRuntime,
) -> QAService:
    return summary_runtime.build_qa_service()


@pytest.fixture()
def atlas_summary_doc_ids(indexed_qa_env: tuple[Engine, Path, Path]) -> list[str]:
    engine, _, _ = indexed_qa_env
    with session_scope(engine) as session:
        statement = (
            select(DocumentModel.doc_id, DocumentModel.display_path)
            .where(DocumentModel.display_path.like("%atlas/%"))
            .where(~DocumentModel.display_path.like("%release_plan%"))
            .order_by(DocumentModel.display_path.asc())
        )
        return [row.doc_id for row in session.execute(statement)]


@pytest.fixture()
def aurora_doc_ids(indexed_qa_env: tuple[Engine, Path, Path]) -> list[str]:
    engine, _, _ = indexed_qa_env
    with session_scope(engine) as session:
        statement = (
            select(DocumentModel.doc_id)
            .where(DocumentModel.display_path.like("%aurora/%"))
            .order_by(DocumentModel.display_path.asc())
        )
        return [row.doc_id for row in session.execute(statement)]
