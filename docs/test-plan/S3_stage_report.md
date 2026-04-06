# S3 阶段完成报告：扫描、全量索引与增量更新

## 1. 新增/修改文件列表

本节只记录当前仓库中仍然存在、且仍由 S3 主链路消费的 owner / 交付物快照。历史迁移前路径和废弃 helper 只能写入后续修复记录，不能继续冒充当前交付物。

### 新增源码（10）
- `src/opendocs/app/source_service.py` — 根目录管理（add/scan/list）
- `src/opendocs/app/index_service.py` — 索引编排（full/incremental/rebuild）+ `index_incremental` 审计
- `src/opendocs/app/_audit_helpers.py` — 两阶段审计（DB + JSONL）
- `src/opendocs/indexing/scanner.py` — 文件系统扫描 + ExcludeRules + unsupported 双写到 excluded_paths
- `src/opendocs/indexing/index_builder.py` — 三阶段索引管线
- `src/opendocs/indexing/watcher.py` — watchdog 监听 + 防抖 + event_type 透传 + watcher_event 审计 + delete 路径 resolve
- `src/opendocs/indexing/hnsw_manager.py` — HNSW 向量索引管理
- `src/opendocs/storage/repositories/source_repository.py` — SourceRoot CRUD
- `src/opendocs/storage/repositories/scan_run_repository.py` — ScanRun CRUD
- `src/opendocs/storage/schema/0002_source_roots_and_scan_runs.sql` — S3 DDL 迁移

### 新增测试（5 + 12 语料）
- `tests/integration/indexing/conftest.py` — 共享 fixture
- `tests/integration/indexing/test_full_index.py` — TC-001 + TC-002 + 排除规则 + unsupported∈excluded
- `tests/integration/indexing/test_incremental.py` — TC-003 + TC-004 + 文件修改 + 增量审计
- `tests/integration/indexing/test_rebuild_idempotent.py` — 重建幂等 + rebuild 重试失败文件
- `tests/integration/indexing/test_watcher.py` — watcher 新增/修改/删除检测 + watcher 审计
- `tests/fixtures/generated/corpus_main/` — 12 个测试文档

### 已修改文件（7）
- `src/opendocs/domain/models.py` — 新增 SourceRootModel、ScanRunModel、AUDIT_OPERATIONS S3 扩展
- `src/opendocs/storage/repositories/__init__.py` — 导出 SourceRepository、ScanRunRepository
- `src/opendocs/indexing/__init__.py` — 导出 Scanner、IndexBuilder、HnswManager 等
- `src/opendocs/app/__init__.py` — 懒加载导出 IndexService、SourceService
- `src/opendocs/utils/logging.py` — 审计日志增强
- `scripts/rebuild_index.py` — 改用 IndexService.rebuild_index()
- `tests/unit/storage/test_migrations.py` — 适配 0002 迁移

### 新增文档（1）
- `docs/test-plan/S3_stage_report.md` — 本文件

## 2. 关键实现说明

### 三阶段索引管线（IndexBuilder）
- Phase A（SQLite WAL 事务）：parse → hash 比较 → chunk → upsert documents/chunks → FTS5 trigger → audit_logs
- Phase B（事务提交后）：flush audit.jsonl
- Phase C（尽力而为）：HNSW add_chunks，失败则 mark_dirty
- 目录事实在 Phase A 一次性推导并落入 `documents.directory_path / relative_directory_path`，后续查询不再从 `path` 临时切割。

### Scanner unsupported 双写
- 不支持的文件格式同时进入 `excluded_paths`（满足 FR-001 "记入排除清单"）和 `unsupported_paths`（保留诊断信息）
- ScanResult 接口零改动

### Watcher event_type 透传链路
- `_DebouncedHandler._process()` → `callback_index(scanned, event_type)` → lambda 转发 → `_on_file_changed(scanned, source, event_type)`
- delete 路径独立，event_type 固定为 `"deleted"`
- 每次 watcher 事件后写入 `operation="watcher_event"` 审计记录；该记录以 `source_root_id` 作为审计目标，文件身份落在 detail

### Watcher delete 路径 resolve
- `_on_file_deleted` 中 `path_str` → `str(Path(path_str).resolve())` 后同时用于查 DB 与写 watcher 审计
- 修复 macOS `/tmp` vs `/private/tmp` 路径不匹配问题
- `status="not_found"` 代表“事件已处理但未命中索引”，只保留在 detail/status，不再把 `result` 误记成失败

### 文件审计路径契约收口
- 新增 `build_file_audit_detail()`，统一为文件型审计写入规范化绝对路径，唯一键为 `detail_json.file_path`
- `AuditRepository.query(file_path=...)` 与写入契约对齐，只按 `detail_json.file_path` 检索，避免继续容忍字段名漂移

### 增量批次审计
- `update_index_for_changes()` 末尾写入 `operation="index_incremental"` 审计（仿 rebuild 模式）
- `detail_json` 含 total/success/failed/skipped/duration

### 失败重试闭环
- `rebuild_index(force=True)` 无条件重处理所有文件（含此前 failed 的），是当前失败重试入口
- `full_index_source` / `update_index_for_changes`（force=False）按 hash 跳过，不检查 parse_status

### S3 收口补记（dense 一致性根因修复）
- 新增 `index_artifacts` SQLite 状态表，明确记录 dense HNSW 工件的 `stale / ready / building / failed`，把“一致性状态”从磁盘启发式收回到数据库。
- `IndexBuilder` 在文档重建/删除的同一事务内先把 dense 工件标记为 `stale`，事务提交后再做 HNSW 增量更新；成功则写回 `ready`，失败则保留 `dirty/failed`。
- 修复了“文档重建只删 SQLite 旧 chunks、不删 HNSW 旧 labels”的深层一致性问题；修改文件后 dense 通道不再残留陈旧片段。
- dirty 补偿重建显式携带 embedder，且旧 64 维或签名不匹配的 HNSW 会在启动时被 DB 状态 + 工件元数据共同触发重建。

## 3. 运行命令

```bash
# S3 集成测试
./.venv/bin/pytest tests/integration/indexing -q

# 门控脚本
./.venv/bin/python scripts/rebuild_index.py --source tests/fixtures/generated/corpus_main

# 单元回归
./.venv/bin/pytest tests/unit/ -q
```

## 4. 测试结果

### 单元测试
```
341 passed
```

### 集成测试
```
39 passed
```

详细测试清单：
- `test_full_index.py`（14 tests）：TC-001 + TC-002，覆盖 source 持久化/扫描统计/scan_run 与 batch audit 关联/按 `file_path` 查询 `index_file` 审计/FTS/HNSW/排除规则/hash 失败落库/unsupported∈excluded
- `test_incremental.py`（11 tests）：TC-003 + TC-004，覆盖新增/修改/删除/parse failure 替换旧索引/增量 audit/scan_run/扫描错误不误删已有文档
- `test_rebuild_idempotent.py`（8 tests）：重建两次一致/scan_run 与 rebuild audit 对齐/无重复/HNSW/修改后更新/rebuild 重试失败文件/dense dirty 补偿
- `test_watcher.py`（6 tests）：新文件检测/删除检测/修改检测/watcher 审计可按规范化 `file_path` 查询/`source_root_id` 目标稳定/删除未命中(`deleted` + `not_found`)审计/启停

### 门控脚本
```
Rebuild complete: 9 success, 2 failed, 0 skipped, hnsw=synced, duration=0.1s
EXIT_CODE=0
```

## 5. 已知问题与风险

| 问题 | 严重度 | 说明 |
|------|--------|------|
| 增量不重试 hash 不变的失败文件 | 中 | `force=False` 路径按 hash 跳过，不检查 parse_status。rebuild 是重试路径。这是设计简化，不以测试固化，后续可增强"仅重试失败文件" |
| 系统默认查看器对 PDF `#page=` 支持不一致 | 低 | 证据页码已透传，但最终能否跳页依赖宿主系统 |
| 旧开发库若保留根因修复前的 schema 将被直接拒绝 | 低 | 当前项目无历史用户数据，脚本与 CLI 会要求重建本地数据库，而不是继续兼容旧脏库 |
| watcher 测试依赖 sleep 等待 | 低 | debounce 0.3s + sleep 2.0s，CI 环境可能需要调整 |

## 6. 出口条件判定

| 出口条件 | 判定 | 依据 |
|---------|------|------|
| 初次全量索引可运行 | **通过** | `rebuild_index.py` exit 0，9 success > 0 |
| 文件增删改后索引同步 | **通过** | TC-001~TC-004 + 文件审计路径/目标语义契约收口 + watcher 删除未命中审计回归测试全部 39 passed |
| 重建索引幂等 | **通过** | TestRebuildIdempotent 8 tests passed（含 rebuild 重试与 dense 补偿回归） |

## 7. 下一阶段计划

S4：混合检索与证据定位
- FTS5 + dense fusion 检索管线
- 目录/分类/标签/时间/敏感级过滤器
- 统一引用结构、quote_preview 与源文件定位
- SearchService 与最小搜索展示壳
- 黄金查询集 Top10 命中率测试

## 8. 2026-03-20 审查修复

- **修复**：`full_index_source()` 现在复用 `SourceService.scan_source()`，首次全量索引会稳定生成 `scan_run`、`scan_source` 审计，并沿用同一 `trace_id` 串起后续索引批次。
- **修复**：新增全量批次级 `operation="index_full"` 审计，补齐首次全量索引缺失的批次链路。
- **修复**：`IndexBuilder.index_file()` 的哈希/读取失败路径不再只留内存结果；现在会把对应文档落成 `parse_status='failed'`，同时清理旧 chunks，并写入失败审计。
- **修复**：`IndexBuilder._upsert_document()` 统一写入规范化目录事实，确保目录过滤的数据来源固定且可追踪。
- **测试**：补充集成测试，覆盖“首次全量索引的 scan_run 与 batch audit 关联”“哈希失败文件仍会落库为 failed 文档”两条回归路径。

## 9. 2026-04-02 S3 根因修复

- **修复**：`documents.file_identity` 改为“仅约束 active 行唯一”的部分索引。deleted 文档保留历史 provenance，但不再占用当前文件身份，也不允许被 `file_identity` 误复活。
- **修复**：`DocumentRepository.get_by_file_identity()` 默认只看 active 文档，配合新增迁移 `src/opendocs/storage/schema/0012_documents_active_file_identity.sql`，把“历史 deleted lineage”和“当前活动 lineage”从数据约束层分开。
- **修复**：`IndexBuilder.index_batch()` 新增批次级 active snapshot 解析。增量索引现在以前一轮 active 文档集和本轮 scan 为输入统一决算，不再受文件处理顺序影响；“改名后原路径被新文件复用”会稳定保留旧 lineage 并创建新 lineage。
- **修复**：`SourceService.add_source()` 拒绝与现有 active source root 重叠的目录，避免一个文件被多个 root 静默争抢所有权。
- **测试**：补充回归覆盖“nested source root 拒绝”“deleted lineage + file_identity reuse 不复活”“path reuse 不打断 rename lineage”，并让 ORM/迁移一致性测试识别部分索引。

## 10. 2026-04-02 S3 并发状态机修复

- **修复**：`IndexWatcher` 不再让多个 debounce timer 线程直接调用 `IndexBuilder`。文件系统事件现在统一先落入 watcher 内部事件队列，再由单个 worker 串行消费；`watchdog` 只负责发“变化信号”，不再直接拥有索引写入权。
- **修复**：dense HNSW 工件现在增加进程内互斥边界。`ensure_index / add / delete / query / rebuild / repair` 全部通过 `HnswManager` 内部锁串行化，避免 `_label_map / _next_label / vector_store / 索引文件` 在并发增量更新时被交叉写坏。
- **修复**：S3 的派生工件生命周期被重新收口为统一状态机：`fs_event -> queue -> SQLite source of truth -> HNSW derived update / mark_dirty -> audit`。这样失败恢复仍然走既有 dirty/rebuild 路径，但中途不会再留下两个线程同时推进同一工件状态的非法转移。
- **测试**：新增 watcher 回归，显式断言突发多文件事件下 `IndexBuilder.index_file()` 的并发度始终为 `1`，把“单写者”约束固化进自动化测试。

## 11. 2026-04-06 S3 交付基线契约补强

- **根因**：阶段报告此前主要靠人工维护，没有自动化约束去证明“当前报告里写的 owner/交付物”和“仓库里真实存在、真实消费的实现”仍然一致；一旦路径迁移或 owner 变更，文档就会先漂移。
- **修复**：新增 `tests/unit/indexing/test_s3_stage_report_contract.py`，把 S3 的当前 owner 快照、`documents.file_identity` 的 active-only 约束语义、以及 `fs_event -> queue -> SQLite source of truth -> HNSW derived update / mark_dirty -> audit` 状态机描述固化成测试契约。
- **修复**：阶段报告顶部现在明确声明“只记录当前仓库仍承担 S3 主链路职责的 owner / 交付物快照”，不再允许历史 helper 和旧路径继续混入当前交付口径。
- **测试**：新增阶段报告契约回归，逐条校验报告中引用的仓库路径真实存在，并且关键状态机描述没有回退成旧口径。
