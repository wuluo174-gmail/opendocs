# OpenDocs 架构概览

> 本文件是 S0 阶段的架构基线记录，随各阶段推进持续更新。

## 一句话定义

OpenDocs 是一个运行在个人电脑上的本地优先 AI 文档助理，专注于扫描、索引、检索、问答、摘要、分类、归档、生成与审计文本类工作文档，所有事实性输出必须能回溯到文档证据。

## 架构风格

MVP 采用**模块化单体（modular monolith）**，而非微服务。
详细决策见 `docs/adr/0001-baseline.md`。

## 分层结构

```
┌─────────────────────────────────────────┐
│  Desktop UI  (PySide6)                  │  ← 只通过 app/ 触发业务，禁止直连底层
├─────────────────────────────────────────┤
│  Application Service Layer  (app/)      │  ← 业务编排，协调各领域模块
├──────────┬──────────┬───────────────────┤
│ domain/  │ parsers/ │ indexing/         │  ← 领域模型 / 解析器 / 索引
│ retrieval│ qa/      │ generation/       │  ← 检索 / 问答 / 生成
│ memory/  │ audit/   │ classification/   │  ← 记忆 / 审计 / 分类
│ provider/│ config/  │ utils/            │  ← 模型路由 / 配置 / 工具
├─────────────────────────────────────────┤
│  Storage Layer  (storage/)              │  ← SQLite + FTS5 + HNSW + 派生工件状态
└─────────────────────────────────────────┘
```

## 锁定技术栈（S0 基线）

| 组件 | 选型 | 版本约束 |
|------|------|---------|
| 语言 | Python | 3.11（锁定） |
| 桌面 UI | PySide6 | >=6.8,<7.0 |
| 数据校验 | Pydantic | v2 |
| 数据库 | SQLite 3 + FTS5 | 内置 |
| ORM | SQLAlchemy | 2.x |
| 向量索引 | hnswlib | 0.8.x |
| 文件监听 | watchdog | 4.x |
| 文档解析 | python-docx / PyMuPDF / pypdf | 见 pyproject.toml |
| 模板 | Jinja2 | 3.x |
| 密钥存储 | keyring | 25.x |
| 测试 | pytest / pytest-qt / pytest-cov | 见 pyproject.toml |
| 打包 | PyInstaller | 6.x |

替换任何锁定选型前，必须在 `docs/adr/` 创建对应 ADR。

## 数据流概览

### 索引流
SourceRoot → ScanRun → 文件系统 → 扫描器 → 解析器注册表 → Chunker → SQLite（Document/Chunk/FTS5）+ HNSW 向量索引 + IndexArtifact

### 检索流
用户查询 → FTS5 召回 + 向量召回 → 分数融合 → 候选证据集 → 模型生成答案 → 引用校验器 → 带引用回答

### 归档流
用户选择 → 分类器 → FileOperationPlan（draft，含逐项变更/依据摘要/风险/回滚最小信息）→ 预览确认 → 执行（move/rename/create）→ AuditLog

## 安全红线（不可违背）

- `delete` 默认无入口
- 所有物理写操作必须经过：预览 → 确认 → 执行 → 审计 → 可回滚
- UI 层禁止直接操作数据库、文件系统、模型提供商
- `MemoryItem` 不得作为事实性引用替代文档证据
- Local-Only 模式下零外发请求
- API Key 不得落入日志或明文配置

## 本地运行目录约定

| 平台 | 路径 |
|------|------|
| macOS | `~/Library/Application Support/OpenDocs/` |
| Windows | `%APPDATA%/OpenDocs/` |
| Linux | `~/.local/share/OpenDocs/` |

内部结构：`config/settings.toml`、`data/opendocs.db`、`index/hnsw/`、`logs/`、`rollback/`、`output/`
