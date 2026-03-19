# 阶段 S1 完成报告

> 最后更新：2026-03-06（合并 18 轮迭代修订为最终状态报告）

## 1. 新增 / 修改文件

### 新增
- `src/opendocs/domain/models.py` — 7 个 ORM 模型（Document, Chunk, KnowledgeItem, RelationEdge, MemoryItem, FileOperationPlan, AuditLog）
- `src/opendocs/storage/db.py` — 数据库初始化、迁移引擎、会话管理
- `src/opendocs/storage/schema/0001_initial.sql` — 全量建表（7 表 + FTS5 虚拟表 + 触发器），含所有约束
- `src/opendocs/storage/repositories/` — 7 个仓储实现（document, chunk, knowledge, relation, memory, plan, audit）
- `src/opendocs/app/file_operation_service.py` — 计划审批与执行闭环服务
- `src/opendocs/utils/time.py` — UTC 时间工具（`utcnow_naive()`）
- `src/opendocs/exceptions.py` — 14 个业务异常类（含规范 §11.3 全部错误码）
- `scripts/init_db.py` — 数据库初始化 CLI 脚本
- `scripts/seed_demo_data.py` — 样例数据种子脚本（幂等）
- `tests/unit/storage/` — conftest、CRUD、迁移、约束、一致性、服务、种子、事务测试
- `docs/adr/0002-source-root-deferred-to-s3.md`
- `docs/adr/0003-dual-track-schema.md`
- `docs/adr/0004-single-db-for-mvp.md`
- `docs/adr/0005-audit-target-type-extension.md`
- `docs/adr/0006-file-operation-service-in-s1.md`
- `docs/adr/0007-fts5-chinese-tokenizer.md`

### 修改
- `src/opendocs/cli/main.py` — 补齐运行目录骨架（config, data, index, rollback, output, temp）
- `src/opendocs/utils/__init__.py` — 导出 `utcnow_naive`
- `.env.example` — 补充 OPENDOCS_CONFIG 说明
- `settings.example.toml` — 完善配置模板
- `README.md` — 补充 S1 命令与 FAQ
- `tests/unit/test_smoke.py` — 扩展异常体系与目录骨架断言

## 2. 关键实现说明

### 数据模型
- 7 个 ORM 模型完整对齐规范 §8.1，Chunk 额外增加 `created_at`/`updated_at`（规范 §2.1 可追踪要求）
- 所有 UUID 字段有格式 CHECK 约束（36 字符、连字符位置、小写十六进制）
- SHA256 哈希有 64 位小写十六进制 CHECK 约束
- `audit_logs.target_type` 预扩展为 10 个值（ADR-0005），避免后续阶段需要 ALTER

### 存储层
- 双轨 Schema 维护（ADR-0003）：ORM 模型和 SQL 迁移各维护一份，通过 `test_schema_consistency.py` 自动检测偏离
- FTS5 虚拟表 `chunk_fts` 通过 INSERT/UPDATE/DELETE 触发器与 chunks 表保持同步
- 迁移框架：原子化应用（BEGIN IMMEDIATE + COMMIT），支持幂等重放、失败安全、版本去重
- PRAGMA：foreign_keys=ON, journal_mode=WAL, busy_timeout=5000

### 仓储层
- 7 个 Repository 覆盖完整 CRUD，支持后续应用服务复用
- 删除策略按风险分层：业务仓储默认禁用（需显式 `allow_delete=True`），审计仓储完全禁删并保持 append-only
- MemoryRepository 拒绝 M0 持久化（规范 §4.4）
- PlanRepository 状态机保护：外部不可直接设 `executed` 状态

### 服务层
- FileOperationService 实现"approve → execute → audit"闭环
- 执行成功和失败均写审计日志
- 依赖注入支持，可注入 mock 仓储进行单测

### 时间处理
- 统一使用 `utcnow_naive()` 生成 UTC naive datetime，微秒截零
- 与 SQLite `datetime('now')` 格式对齐

## 3. 运行命令

```bash
# S1 标准测试序列（tasks.yaml 定义）
python -c "from pathlib import Path; Path('.tmp/opendocs.db').unlink(missing_ok=True)"
python scripts/init_db.py --db-path .tmp/opendocs.db
python scripts/seed_demo_data.py --db-path .tmp/opendocs.db
pytest tests/unit/storage -q

# 全量回归
pytest -q
```

## 4. 测试结果

- 全量测试：**101 passed**
- 存储层测试：**76 passed**
- `ruff check .`：全绿
- S1 命令序列（init_db → seed → storage tests）：全绿

### 测试覆盖分布
| 测试文件 | 数量 | 覆盖内容 |
|---------|------|---------|
| test_repositories_crud.py | 22 | 7 个仓储的完整 CRUD + update_indexed_at/mark_deleted_from_fs/delete_by_doc_id |
| test_migrations.py | 27 | 建表、约束、FTS 触发器、幂等、原子性、init_db 脚本、chunk_index 非负、时间格式 |
| test_models_constraints.py | 17 | ORM CHECK 约束拒绝（含 src_type/dst_type、chunk_index 非负） |
| test_schema_consistency.py | 6 | ORM↔SQL 表/列/索引/约束一致性 |
| test_file_operation_service.py | 6 | 服务层审批执行闭环 |
| test_seed_demo_data.py | 4 | 种子幂等与路径隔离 |
| test_transaction_rollback.py | 2 | 事务提交与回滚 |

## 5. 已知问题 / 风险

| 级别 | 问题 | 记录位置 | 解决阶段 |
|------|------|---------|---------|
| P1 | FTS5 中文分词器使用默认 unicode61，中文搜索效果差 | ADR-0007 | S3/S4 |
| ~~P2~~ | ~~`relation_edges.src_type/dst_type` 缺枚举 CHECK 约束~~ | ~~本报告~~ | **已修复** |
| P2 | `AuditRepository.query` 的 json_extract 无索引，大量数据时性能差 | 本报告 | S6/S11 |
| P2 | `PlanRepository._internal` 参数是临时权限边界 | ADR-0006 | S6 |
| P3 | `chunks.created_at/updated_at` 和 `knowledge_items.created_at/updated_at` 为实现补充字段，规范 §8.1 未定义 | 本报告 | 保留（§2.1 可追踪要求） |

## 6. 出口条件判定

- [x] 可初始化数据库
- [x] 可写入 / 查询核心实体
- [x] 自动化测试覆盖 CRUD 与迁移

## 7. 下一阶段计划

S2：解析器与切片器
- 定义 parser 接口与 ParsedDocument 模型
- 实现 txt/md/docx/pdf 四类解析器
- 实现 heading/paragraph 优先切片
- 解析失败隔离
- 补齐测试

## 8. 修订记录

### 2026-03-06 代码审查修复（第一轮）
- 为 `relation_edges.src_type/dst_type` 添加 CHECK 约束（ORM + SQL 双轨同步），枚举值：`document/chunk/knowledge/memory/entity/topic`
- 为 `DocumentRepository` 补充 `update_indexed_at()` 和 `mark_deleted_from_fs()` 方法，支持 S3 增量索引复用
- 为 `ChunkRepository` 补充 `delete_by_doc_id()` 批量删除方法，支持 S3 重建索引复用
- 补充 5 个对应单元测试（src_type/dst_type 约束拒绝 × 2、update_indexed_at、mark_deleted_from_fs、delete_by_doc_id）
- 全量测试 93 → 98，存储层测试 68 → 73

### 2026-03-06 代码审查修复（第二轮）
- **修复**：`db.py` 中 `isoformat()` 生成含 `T` 的时间格式，违反 ADR-0003 约定；改为 `strftime("%Y-%m-%d %H:%M:%S")`
- **修复**：`chunks.chunk_index` 缺少 `>= 0` 非负约束；在 SQL 和 ORM 双轨同步添加 CHECK
- **修复**：`FileOperationService` 失败审计中 `error` key 可能覆盖调用方已有 key；改为 `exec_error`
- **改善**：为 `Document.created_at/modified_at` 添加注释，明确 S3 必须传入文件系统时间而非默认值
- **测试**：新增 chunk_index 非负约束测试（ORM + SQL 各 1 个）、migration 时间格式测试
- 全量测试 98 → 101，存储层测试 73 → 76

### 2026-03-13 审查收口修复
- **修复**：`MemoryRepository.create()` 新增 `M0` 持久化守卫，直接仓储调用也会拒绝将会话记忆落盘，对齐主规范 §4.4“`M0` 会话记忆不持久化”
- **修复**：`AuditRepository` 收口为 append-only：`update_detail()` 直接拒绝原地改写，`delete()` 始终拒绝删除，避免仓储层绕过审计红线
- **测试**：补充仓储层单测，覆盖 `MemoryRepository` 直接拒绝 `M0` 入库，以及 `AuditRepository` 的“更新拒绝 / 删除始终拒绝”路径

## 9. ADR 索引

| ADR | 标题 | 状态 |
|-----|------|------|
| 0001 | 技术基线锁定 | S0 已接受 |
| 0002 | SourceRoot 延迟到 S3 | S1 已接受 |
| 0003 | ORM/SQL 双轨维护 | S1 已接受 |
| 0004 | MVP 单库简化 | S1 已接受 |
| 0005 | 审计 target_type 预扩展 | S1 已接受 |
| 0006 | FileOperationService 提前到 S1 | S1 已接受 |
| 0007 | FTS5 中文分词器选型延迟 | S1 已接受 |
