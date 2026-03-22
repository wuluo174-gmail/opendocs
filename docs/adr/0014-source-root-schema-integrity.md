# ADR-0014: SourceRoot schema integrity takes precedence over placeholder UUIDs

- 状态：Accepted
- 日期：2026-03-20
- 阶段：S1 / S3 根因修复
- supersedes: ADR-0002

## 背景

ADR-0002 允许在 S1/S2 阶段把 `documents.source_root_id` 当作“占位 UUID”，等到 S3 再真正引入 `source_roots`。这在实现上带来了三个已经发生的问题：

1. `Document.source_root_id` 的数据来源不清晰，脚本和测试可以随意写入任意 UUID。
2. SQLite schema 层无法证明 `documents` 与 `scan_runs` 确实挂在真实的来源根目录上，容易出现孤儿文档和失联的扫描记录。
3. 为了兼容这种宽松设计，修复会倾向于引入触发器补丁、占位来源对象、假哈希等“看起来可用但来源不真实”的数据。

结合“数据从哪里来”的核心三问：

1. 数据从哪里来？
   `source_root_id` 只能来自已持久化的 `source_roots`。
2. 谁负责写入？
   只能由 `SourceService`、seed 脚本或测试 fixture 先创建 `source_roots`，再写入 `documents` / `scan_runs`。
3. 如何证明它是对的？
   必须由 SQLite 外键、ORM 约束和自动化测试共同证明，而不是靠调用方自觉。

本项目当前仍处于开发阶段，**没有历史用户数据负担**，因此可以直接把约束收回到 schema 源头，而不是继续维护占位 UUID 的兼容路径。

## 决策

1. `source_roots` 允许前移到基础 migration，作为引用完整性的基础表。
2. `SourceService`、扫描、审计、增量更新等业务能力仍然保持在 S3 交付，不提前把 S3 业务逻辑搬到 S1。
3. `documents.source_root_id` 和 `scan_runs.source_root_id` 必须在 SQLite schema 中真实外键到 `source_roots(source_root_id)`。
4. seed、fixture、脚本不得再直接写任意占位 UUID，必须先创建真实 `source_root`。
5. 对于不可读导致无法计算内容哈希的失败文档，`hash_sha256` 允许为 `NULL`，但仅限 `parse_status='failed'`；禁止写入伪造哈希占位值。

## 理由

1. **引用完整性必须来自数据库**
   ORM 上的 `ForeignKey` 不是最终事实，真实约束必须落在 SQLite schema。

2. **阶段纪律与数据纪律可以同时满足**
   前移的是基础持久化约束，不是 S3 的业务能力。SourceRoot 的“可管理、可扫描、可审计”仍然是 S3 交付。

3. **开发阶段应优先修根因**
   既然没有历史用户数据，就不应该为了兼容不存在的旧数据而长期保留占位 UUID、触发器补丁或假数据。

4. **防止同类问题再次出现**
   通过 ORM/SQL foreign key 一致性测试，可以把“模型有约束、数据库没约束”的漂移直接卡在测试里。

## 被否决的方案

| 方案 | 否决原因 |
|------|----------|
| 继续沿用占位 UUID，到 S3 再补 | 根因仍在，脚本和测试还会继续制造孤儿数据 |
| 用后补 trigger 守卫 `documents.source_root_id` | 只是补丁，仍然把 schema 真相和业务真相拆开了 |
| 为失败文件写固定伪造哈希 | 违反“数据从哪里来”，会把未知值伪装成真实内容哈希 |

## 影响

- `source_roots` 成为基础 schema 的一部分
- `documents` / `scan_runs` 的来源关系可在 SQLite 层直接验证
- 旧的“任意 UUID 作为来源”的测试夹具需要同步收紧
- 开发环境若保留旧临时数据库，需重建数据库以获得新的 schema 约束

## 实施约束

1. 任何新增写入路径都必须先拿到真实 `source_root_id`
2. 不得再通过 migration 补丁生成占位来源对象
3. 不得为未知哈希写入伪造值
4. `test_schema_consistency.py` 必须持续校验 ORM/SQL foreign keys 一致
