# ADR-0005：audit_logs.target_type 枚举预扩展

- 状态：Accepted
- 日期：2026-03-05
- 阶段：S1（记录 S1 设计决策）

## 背景

主规范的 `AuditLog` 数据模型最初只显式列出 `document / plan / memory / answer` 这 4 类 `target_type`。

但主规范的 `FR-013 审计与导出` 明确要求的审计对象远超这 4 类——包括扫描（source）、检索（search）、模型外发（provider_call）、生成（generation）、索引运行（index_run）、回滚（rollback）。如果 S1 只声明 4 个值，S3 扫描审计时就会被 CHECK 约束拦住，需要额外的迁移和约束重建。

## 决策

**在 S1 基线中将 `target_type` 枚举预扩展为 10 个值**：

```
document, plan, memory, answer, source, search, provider_call, generation, index_run, rollback
```

在 ORM `AuditLogModel.__table_args__` 和 `0001_initial.sql` 中同步声明。

## 理由

1. **避免后续阶段迁移复杂度**：SQLite 修改 CHECK 约束需要表重建，代价较高。
2. **符合规范精神**：`FR-013 审计与导出` 已明确列出这些审计类型，预扩展只是将隐含需求显式化。
3. **不引入 S2+ 功能**：仅扩展约束枚举，不实现对应的服务逻辑。

## 需求追踪

| 扩展值 | 来源需求 | 首次使用阶段 |
|--------|----------|-------------|
| `document` | 主规范 `AuditLog` 基础定义 | S1 |
| `plan` | 主规范 `AuditLog` 基础定义 | S1 |
| `memory` | 主规范 `AuditLog` 基础定义 | S8 |
| `answer` | 主规范 `AuditLog` 基础定义 | S5 |
| `source` | FR-001 文档源配置与扫描，FR-013 必审计操作 | S3 |
| `search` | FR-003 混合搜索，FR-013 必审计操作 | S4 |
| `provider_call` | FR-012 隐私模式与模型路由，FR-013 必审计操作 | S10 |
| `generation` | FR-007 知识生成，FR-013 必审计操作 | S7 |
| `index_run` | FR-002 索引构建与增量更新，FR-013 必审计操作 | S3 |
| `rollback` | FR-011 文件操作安全与回滚，FR-013 必审计操作 | S6 |

## 影响

- ORM 和 SQL 的 `target_type` CHECK 枚举保持同步。
- 后续阶段可直接写入新类型的审计日志而不触发约束错误。
