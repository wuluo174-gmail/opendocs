# ADR-0001: OpenDocs 技术基线与 S0 约束

- 状态：Accepted
- 日期：2026-03-03
- 阶段：S0

## 背景

主规范与任务清单已锁定 OpenDocs 技术栈，且要求 S0 完成可运行脚手架、最小入口、测试基线和 CI 基线。

## 决策

1. 运行时与架构基线：
   - Python 3.11（CI 固定）
   - PySide6
   - Pydantic v2
   - SQLite 3 + FTS5
   - SQLAlchemy 2.x
   - hnswlib
   - watchdog
   - python-docx
   - PyMuPDF（pypdf 作为降级）
   - Jinja2
   - pytest / pytest-qt / pytest-cov
   - PyInstaller
   - TOML + env
   - keyring
2. 安装与执行策略：
   - `scripts/bootstrap_dev.py` 必须按 `requirements.lock` 安装依赖，并验证 `hnswlib` 可导入。
   - 锁定基线为 Python 3.11；若在 Windows 下入口解释器不是 3.11，脚本可自动委托 `py -3.11` 重新执行。
   - 若无法使用 Python 3.11 或 `hnswlib` 校验失败，脚本必须返回非 0，避免“降级成功”误判。
3. 任何偏离以上栈或安全红线的变更，必须先新增 ADR 再实施。

## 理由

- 与主规范、tasks.yaml 的锁定栈一致。
- 通过锁文件安装和依赖校验提升可重复性，避免环境漂移。
- 为后续阶段提供稳定、可审计、可测试的统一基线。

## 影响

- S0 安装过程与锁定基线一致，且缺失关键依赖时会显式失败。
- 若后续引入新框架或替换现有基线，必须走 ADR 流程。
