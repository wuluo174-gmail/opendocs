# 阶段 S1 完成报告

## 1. 新增 / 修改文件
- 修改 `scripts/seed_demo_data.py`
- 修改 `tests/unit/storage/test_seed_demo_data.py`
- 新增 `src/opendocs/storage/schema/0004_audit_target_type_guardrail.sql`
- 修改 `tests/unit/storage/test_migrations.py`
- 修改 `docs/acceptance/tasks.yaml`

## 2. 关键实现说明
- 去除 `seed_demo_data.py` 中对仓库根目录 `demo/`、`archive/` 的硬编码。
- 新增 `resolve_seed_paths(db_path)`，将 demo 文档与归档目标路径统一约束到数据库所在目录下（例如 `.tmp/demo/`、`.tmp/archive/`）。
- 保持 seed 幂等：同一 `db-path` 重复运行不会重复写入同一业务键。
- 更新单测，显式断言种子文档路径位于 `db_path.parent`，防止回归到仓库工作区路径。

## 3. 运行命令
- `./.venv/bin/python -c "from pathlib import Path; Path('.tmp/opendocs.db').unlink(missing_ok=True)"`
- `./.venv/bin/python scripts/init_db.py --db-path .tmp/opendocs.db`
- `./.venv/bin/python scripts/seed_demo_data.py --db-path .tmp/opendocs.db`
- `./.venv/bin/pytest tests/unit/storage -q`
- `./.venv/bin/pytest tests/unit/storage`
- `./.venv/bin/pytest`

## 4. 测试结果
- 通过：
  - `./.venv/bin/python -c "from pathlib import Path; Path('.tmp/opendocs.db').unlink(missing_ok=True)"`
  - `./.venv/bin/python scripts/init_db.py --db-path .tmp/opendocs.db`（应用 `0001,0002,0003,0004`）
  - `./.venv/bin/python scripts/seed_demo_data.py --db-path .tmp/opendocs.db`
  - `./.venv/bin/pytest tests/unit/storage -q`
  - `./.venv/bin/pytest tests/unit/storage`（33 passed）
  - `./.venv/bin/pytest`（54 passed）
- 失败：
  - 无
- 覆盖范围：
  - S1 迁移、CRUD、事务回滚、seed 幂等与路径隔离

## 5. 已知问题 / 风险
- 若跳过“先清理临时 DB”命令，复用已有 `.tmp/opendocs.db` 时 seed 插入计数会受历史数据影响（功能正确，但计数不一定全为 1）。

## 6. 出口条件判定
- [x] 可初始化数据库
- [x] 可写入 / 查询核心实体
- [x] 自动化测试覆盖 CRUD 与迁移

## 7. 下一阶段计划
- 不进入 S2；等待你确认后再按阶段推进。

## 8. 2026-03-04 修订记录
- 修正 `docs/acceptance/tasks.yaml` 中 S1 的 `acceptance_refs`，移除 `TC-017`，避免与 S10 的 keyring 实施阶段定义冲突。
- 为 S1 阶段测试命令增加临时 DB 清理步骤，确保复验输出稳定。
- 同步更新全量回归测试记录为 `pytest -q`（45 passed）。
- 补齐 S1 强约束空档：新增 `char_end >= char_start`、`ttl_days >= 0（可空）`、`item_count >= 0`，并在 ORM 与 `0001_initial.sql` 同步表达。
- 将 `0002_audit_target_type_check.sql` 调整为兼容标记（no-op），消除与 `0001` 的重复约束迁移噪音。
- 新增 `0003_storage_guardrails.sql`，通过触发器为旧库补强上述约束，并补齐迁移/约束单测。
- 新增 `0004_audit_target_type_guardrail.sql`，为历史库补齐 `audit_logs.target_type` 枚举约束触发器。
- 补充迁移回归测试：模拟已标记 `0001` 的历史库升级到最新版本，断言非法 `target_type='chunk'` 会被拒绝。
- 修正 S1 的验收映射语义漂移：`acceptance_refs` 调整为 `[]`，避免引用需要 S3+ 能力前置条件的 `TC-016`。
- 为五类仓储的 `delete` 增加“默认禁用”保护：未显式 `allow_delete=True` 时抛出 `PermissionError`。
- 同步 CRUD 单测：新增默认拒绝断言，并保留显式允许后的删除路径覆盖。
