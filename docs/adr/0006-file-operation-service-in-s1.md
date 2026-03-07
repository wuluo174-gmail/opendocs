# ADR-0006: S1 阶段提前引入 FileOperationService

## 状态

已接受

## 上下文

规范 §16 阶段 1 的目标是"领域模型与存储基线"，核心交付物为 ORM 模型、迁移系统、仓储层 CRUD。
`FileOperationService` 属于应用服务层（`src/opendocs/app/`），严格来说应在 S6（分类、归档计划与回滚）实现。

## 决策

在 S1 阶段提前引入 `FileOperationService`，原因如下：

1. **plan + audit 闭环测试**：规范 §8.2 第 4、5 条要求"所有 move/rename/create 必须先生成 FileOperationPlan"和"所有执行过的写操作必须有对应 AuditLog"。这两个数据不变量需要在仓储基线阶段就有测试覆盖，否则 S6 之前的仓储层 API 设计可能偏离。
2. **状态机保护**：`PlanRepository.update_status("executed")` 的外部调用需要被阻断，这个保护逻辑与仓储层设计直接耦合，推迟到 S6 会造成仓储 API 语义漂移。
3. **最小实现**：当前 `FileOperationService` 仅包含 `approve_plan` 和 `execute_plan` 两个方法，不包含分类、路径规划、文件系统操作等 S6 业务逻辑。

## 影响

- S1 的 `src/opendocs/app/` 目录多出一个文件，但不引入 S2+ 业务功能。
- S6 实现时将在此基础上扩展，而非重新设计。

## 回退方案

若后续发现提前引入造成了 API 锁定问题，可在 S6 开始前将 `FileOperationService` 的状态机逻辑下沉到 `PlanRepository`，删除 `_internal` 参数。
