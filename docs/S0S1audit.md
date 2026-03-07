# S0/S1 审查报告

> 审查日期：2026-03-06（第二轮增量审查）
> 审查方法：第一性原理逐文件代码阅读 + 对照主规范/tasks.yaml/acceptance_cases.md
> 审查范围：仅 S0（项目脚手架与基线）和 S1（领域模型与存储基线）

---

## 1. 审查结论

**S0 和 S1 均已达标，第二轮审查发现 2 个 Minor 问题并已修复。**

- 101 项单元测试全部通过（1.44s）
- `ruff check` + `ruff format` 全绿（59 files）
- CLI 入口正常（`python -m opendocs --help/--version`）
- 所有交付物齐备，出口条件全部满足

---

## 2. S0 逐项检查

### S0-T01: 仓库目录与占位模块

| 检查项 | 结果 |
|--------|------|
| 仓库结构符合主规范 §7.1 | PASS — src/opendocs, tests/unit, scripts, docs/adr, docs/acceptance 等均存在 |
| src/opendocs 可导入 | PASS — `__init__.py` 定义 `__version__ = "0.1.0"` |
| tests/ 与 scripts/ 齐备 | PASS — tests/unit/storage/, scripts/bootstrap_dev.py 等均存在 |
| §7.1 所有子目录占位 | PASS — tests/integration, tests/e2e, tests/performance, tests/fixtures, tests/golden 均存在 |

### S0-T02: pyproject、开发依赖、lint/format/pytest 配置

| 检查项 | 结果 |
|--------|------|
| pip install -e .[dev] 可执行 | PASS — pyproject.toml 正确配置 setuptools + src layout |
| pytest 可空跑 | PASS — 101 tests collected and pass |
| 静态检查配置已落地 | PASS — ruff 配置在 pyproject.toml，`ruff check` + `ruff format` 全绿 |
| 锁定技术栈匹配 | PASS — Python 3.11, Pydantic v2, SQLAlchemy 2.x, keyring, PySide6, pytest, ruff |
| stack 可选依赖分组 | PASS — watchdog, hnswlib, python-docx, PyMuPDF, pypdf, Jinja2, pyinstaller 在 [stack] 中 |

### S0-T03: 配置加载、日志初始化、异常基类、应用入口

| 检查项 | 结果 |
|--------|------|
| python -m opendocs 可启动 | PASS — 输出 "OpenDocs baseline started." |
| 日志目录与默认配置路径可解析 | PASS — `resolve_app_root()` 支持 Windows/macOS/Linux |
| 基础异常体系可复用 | PASS — 12 个业务异常类覆盖 §11.3 所有错误码 + DeleteNotAllowedError |
| settings.example.toml 匹配 §19.1 | PASS — 完全一致 |
| 配置使用 Pydantic v2 | PASS — `OpenDocsSettings` 5 个子模型 (app/index/retrieval/memory/provider) |
| CLI 创建 §7.2 运行目录骨架 | PASS — config/logs/data/index/hnsw/index/cache/rollback/output/temp |
| 日志 JSON 格式化 + 敏感信息脱敏 | PASS — RedactFilter 拦截 api_key/token/password/secret/Bearer/sk- |

### S0-T04: README、ADR-0001

| 检查项 | 结果 |
|--------|------|
| README 覆盖安装、运行、测试、目录结构 | PASS |
| ADR-0001 基线决策存在 | PASS — docs/adr/0001-baseline.md |
| .env.example 存在 | PASS — 文档化 OPENDOCS_CONFIG 环境变量 |
| requirements.lock 存在 | PASS |
| docs/architecture/ 存在 | PASS — 含 overview.md |

### S0-T05: 最小 CI 与 smoke test

| 检查项 | 结果 |
|--------|------|
| smoke test 覆盖异常层级、CLI help、CLI 启动、脚本存在性 | PASS — 8 个 smoke test |
| 运行目录骨架创建测试 | PASS — test_cli_creates_runtime_directory_skeleton |
| 非标准配置路径测试 | PASS — test_cli_uses_non_canonical_explicit_config_root_for_logs |

### S0 出口条件判定

| 出口条件 | 结果 |
|----------|------|
| 本地可安装依赖 | PASS |
| pytest 空跑成功 | PASS — 101 passed |
| python -m opendocs 可启动 | PASS |
| README 写清运行方式 | PASS |

---

## 3. S1 逐项检查

### S1-T01: 7 个领域模型

| 模型 | 字段对齐 §8.1 | CHECK 约束 | 外键 | 索引 |
|------|---------------|------------|------|------|
| DocumentModel | PASS | file_type, parse_status, sensitivity, UUID, SHA256, size_bytes | — | source_root_id, hash_sha256 |
| ChunkModel | PASS | chunk_index>=0, char_end>=char_start, UUID | doc_id FK CASCADE | doc_id, embedding_key |
| KnowledgeItemModel | PASS | UUID, confidence [0,1] | doc_id FK, chunk_id FK CASCADE | doc_id, chunk_id |
| RelationEdgeModel | PASS | src_type, dst_type, relation_type, weight>=0, UUID | evidence_chunk_id FK SET NULL | src, dst, evidence_chunk_id |
| MemoryItemModel | PASS | memory_type, scope_type, status, importance [0,1], ttl_days>=0, UUID | — | UNIQUE(type,scope_type,scope_id,key) |
| FileOperationPlanModel | PASS | operation_type, status, risk_level, item_count>=0, UUID | — | — |
| AuditLogModel | PASS | actor, result, target_type(含扩展值), UUID, trace_id 非空 | — | timestamp, trace_id, target, operation |

**特别验证：**
- ORM 与 SQL 模式一致性：`test_schema_consistency.py` 验证表/列/索引/约束数量匹配 — PASS
- FTS5 虚拟表与 INSERT/UPDATE/DELETE 触发器同步 — PASS
- Cascade delete 正确传播 — PASS
- Relation edge evidence_chunk_id SET NULL 行为 — PASS
- 额外字段（created_at/updated_at）合理补充，不违反规范 — PASS

### S1-T02: 数据库初始化、迁移与连接管理

| 检查项 | 结果 |
|--------|------|
| init_db 可在新目录下创建数据库 | PASS |
| 迁移脚本可重复执行（幂等） | PASS — `test_migrate_is_idempotent` |
| 迁移失败原子回滚 | PASS — `test_migration_failure_is_atomic` |
| 迁移失败后可重试 | PASS — `test_migration_failure_leaves_db_usable_for_retry` |
| 重复版本号前缀检测 | PASS — `test_migrate_fails_fast_on_duplicate_version_prefixes` |
| PRAGMA 设置（foreign_keys, WAL, busy_timeout） | PASS — 在 `_connect_sqlite` 和 `build_sqlite_engine` 中一致 |
| 时间戳格式一致性（ADR-0003） | PASS — `test_migration_timestamp_format_no_iso_t` |
| 单一初始迁移文件 0001_initial.sql | PASS — 合并为单文件，旧增量迁移已删除 |

### S1-T03: 仓储接口与基础 CRUD

| 仓储 | Create | Read | Update | Delete | 安全红线 |
|------|--------|------|--------|--------|----------|
| DocumentRepository | PASS | get_by_id, get_by_path, list_all | update_title, update_indexed_at, mark_deleted_from_fs | allow_delete 守卫 | modified_at 不因记录更新而变（§8.1.1 文件系统时间语义） |
| ChunkRepository | PASS | get_by_id, list_by_document, get_by_document_index | update_text | allow_delete + delete_by_doc_id | PASS |
| KnowledgeRepository | PASS | get_by_id, list_by_document | update_summary | allow_delete | PASS |
| RelationRepository | PASS | get_by_id, list_by_source | update_weight | allow_delete | PASS |
| MemoryRepository | PASS | get_by_id, get_by_scope_key, list_active_by_scope | update_status | allow_delete | M0 拒绝持久化 |
| PlanRepository | PASS | get_by_id, list_by_status | update_status(含状态机守卫) | allow_delete | executed 状态必须经 FileOperationService |
| AuditRepository | PASS | get_by_id, query(多维) | update_detail | allow_delete | PASS |

### S1-T04: 样例 seed 数据脚本

| 检查项 | 结果 |
|--------|------|
| seed_demo_data.py 可写入 7 类实体 | PASS |
| 幂等（重复运行不重复插入） | PASS — `test_seed_demo_data_is_idempotent` |
| 自动创建 demo 文档文件 | PASS |
| 处理已有业务键 | PASS — `test_seed_demo_data_handles_existing_business_keys` |

### S1-T05: CRUD、迁移、事务回滚单元测试

| 测试文件 | 测试数 | 覆盖 |
|----------|--------|------|
| test_repositories_crud.py | 20 | 7 个仓储的 CRUD + cascade + M0 拒绝 + scope key unique |
| test_migrations.py | 21 | 表创建、幂等、约束、FTS trigger、原子回滚、重试、init_db.py |
| test_models_constraints.py | 17 | 所有 CHECK 约束、FK、范围校验 |
| test_schema_consistency.py | 6 | ORM-SQL 一致性、时间戳格式、FTS trigger |
| test_file_operation_service.py | 6 | 计划审批、执行、审计、模拟、失败处理 |
| test_seed_demo_data.py | 4 | 插入、幂等、文件创建、已有键处理 |
| test_transaction_rollback.py | 2 | 事务回滚不污染 |

### S1 出口条件判定

| 出口条件 | 结果 |
|----------|------|
| 可初始化数据库 | PASS |
| 可写入/查询核心实体 | PASS |
| 自动化测试覆盖 CRUD 与迁移 | PASS — 76 个存储相关测试 |

---

## 4. 安全红线检查

| 红线 | 结果 |
|------|------|
| delete 默认禁用 | PASS — 所有 7 个仓储 delete 方法均需 `allow_delete=True` |
| 未确认不执行物理写操作 | PASS — `FileOperationService` 强制 draft→approved→executed |
| M0 不持久化 | PASS — `MemoryRepository.create()` 拒绝 M0 |
| API key 不落盘 | PASS — settings.example.toml 无密钥字段；RedactFilter 脱敏日志 |
| 审计链路完整 | PASS — 每次 plan 执行自动生成 AuditLog |

---

## 5. ADR 记录

共 7 个 ADR 文档已归档：

| ADR | 主题 |
|-----|------|
| 0001 | 基线技术栈锁定 |
| 0002 | source_root 推迟到 S3 |
| 0003 | 双轨 schema 与时间格式约定 |
| 0004 | MVP 单库策略 |
| 0005 | audit target_type 扩展 |
| 0006 | FileOperationService 在 S1 落地 |
| 0007 | FTS5 中文分词策略 |

---

## 6. 发现的问题与修复

### 第一轮审查（2026-03-06 早期）

**问题 #1: test_document_update_indexed_at docstring 与行为矛盾**

- 文件：`tests/unit/storage/test_repositories_crud.py:113`
- 严重性：Minor
- 描述：docstring 写 "refresh modified_at"，但实现正确地**不**修改 `modified_at`（§8.1.1 规定它是文件系统 mtime）。断言使用 `>=` 掩盖了矛盾。
- 修复：将 docstring 改为 "NOT change modified_at (§8.1.1 file-system mtime)"，将断言从 `>=` 改为 `==`。
- 验证：101 个测试全部通过。

### 第二轮审查（2026-03-06 增量）

**问题 #2: `ruff format` 不通过 — `models.py` 格式不合规**

- 文件：`src/opendocs/domain/models.py:25`
- 严重性：Minor（NFR-019 静态检查要求全通过）
- 描述：`AUDIT_OPERATIONS = frozenset({...})` 的括号嵌套格式不符合 ruff format 规范（`frozenset` 调用和 `{` 应换行缩进）。
- 修复：按 ruff format 规范重排为 `frozenset(\n    {\n        ...\n    }\n)` 格式。
- 验证：`ruff format --check` 通过（59 files already formatted）。

**问题 #3: `ruff check` E501 行过长**

- 文件：`tests/unit/storage/test_repositories_crud.py:114`
- 严重性：Minor（NFR-019 静态检查要求全通过）
- 描述：docstring 行长 102 字符，超过 `pyproject.toml` 中设定的 `line-length = 100` 限制。
- 修复：将 docstring 缩短为 `"""update_indexed_at sets indexed_at but NOT modified_at (§8.1.1)."""`（64 字符）。
- 验证：`ruff check` 全绿（All checks passed!）。

### 6.1 审查确认无问题的关键点

- 7 个 ORM 模型字段完全对齐规范 §8.1
- SQL 迁移与 ORM 一致性由 test_schema_consistency.py 自动守护
- FTS5 触发器（INSERT/UPDATE/DELETE）同步正确
- Cascade delete 与 SET NULL 行为正确
- `utcnow_naive()` 截断微秒，与 SQLite `datetime('now')` 格式兼容（ADR-0003）
- FileOperationService 状态机（draft→approved→executed）不可绕过
- 执行失败写 failed 状态 + failure audit（test_execute_plan_sets_failed_status_on_executor_error）
- 日志脱敏覆盖 api_key / token / password / secret / Bearer / sk- 等模式
- 配置模块支持 TOML + 环境变量覆盖 + Pydantic v2 校验
- 异常体系覆盖主规范 §11.3 所有 10 个错误码 + DeleteNotAllowedError

---

## 7. 后续阶段提示（不在本次审查范围，仅供参考）

- S2 需要实现 parser 接口与 4 类解析器，chunker 切片逻辑
- FTS5 中文分词（ADR-0007）需在 S3/S4 中落地
- source_root 配置表（ADR-0002）在 S3 中补充
