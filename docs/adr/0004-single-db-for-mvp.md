# ADR-0004：MVP 阶段使用单一 SQLite 数据库

- 状态：Accepted
- 日期：2026-03-05
- 阶段：S1（记录 S1 设计决策）

## 背景

早期主规范曾提及数据库分库设计（文档库、知识库、记忆库等），暗示不同领域实体可存储在独立数据库中。

S1 存储基线将所有实体（documents、chunks、knowledge_items、relation_edges、memory_items、file_operation_plans、audit_logs）放在同一个 SQLite 文件中。

## 决策

**MVP 阶段使用单一 SQLite 数据库文件，不做分库。**

## 理由

1. **事务简单性**：单库内所有操作可在同一事务中完成（如写入 plan 同时写入 audit_log），无需跨库事务协调。
2. **查询便利性**：跨表 JOIN（如 document → chunk → knowledge_item）无需 ATTACH DATABASE。
3. **部署简单性**：单文件数据库易于备份、迁移和调试。
4. **MVP 数据量可控**：S1~S3 阶段的数据量远未达到需要分库的规模。

## 复查触发条件

当满足以下任一条件时，应重新评估是否分库：

- 单库文件超过 500MB
- 写入并发需求超过 SQLite WAL 模式的吞吐上限
- 不同实体的备份/清理策略出现本质分歧（如审计日志需 90 天归档而文档库需永久保留）
- 进入多用户/多进程部署模式

## 影响

- 所有 `init_db()` 和 `build_sqlite_engine()` 调用使用同一 `db_path`。
- 未来分库时需新增迁移脚本将数据拆分到独立文件，并修改连接管理逻辑。
