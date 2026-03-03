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
2. 本地开发兼容策略：
   - 为避免阻塞当前开发机，S0 允许本地 Python 3.12 执行。
   - `pyproject.toml` 约束 `>=3.11,<3.13`。
   - CI 工作流固定 Python 3.11 作为规范基线。
3. 任何偏离以上栈或安全红线的变更，必须先新增 ADR 再实施。

## 理由

- 与主规范、tasks.yaml 的锁定栈一致。
- 在不破坏规范的前提下降低本地环境阻塞风险。
- 为后续阶段提供稳定、可审计、可测试的统一基线。

## 影响

- S0 可以在本地和 CI 一致执行核心命令：安装、启动、测试。
- 若后续引入新框架或替换现有基线，必须走 ADR 流程。
