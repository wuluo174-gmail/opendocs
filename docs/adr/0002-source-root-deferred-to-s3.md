# ADR-0002：SourceRoot 实体推迟至 S3 实现

- 状态：Accepted
- 日期：2026-03-05
- 阶段：S1（记录 S1 设计决策）

## 背景

主规范 §8.1（领域对象一览）定义了七个核心实体：Document、Chunk、KnowledgeItem、RelationEdge、MemoryItem、FileOperationPlan、AuditLog。**SourceRoot（文档源根目录）未被列为 S1 领域对象。**

然而，`DocumentModel.source_root_id` 字段（UUID 类型）在 S1 已存在，用于标记文档所属的根目录。这在数据层形成了一个"占位 UUID 字段"而无对应实体表的状态。

S3 的 S3-T01 明确交付 `src/opendocs/app/source_service.py`，其 done_when 要求"可保存多个根目录配置""扫描输出纳入/排除/失败统计""生成 scan_run 与审计记录"。

## 决策

**SourceRoot 表和 SourceService 在 S3 实现，不在 S1 提前创建。**

S1 中 `documents.source_root_id` 保持为 UUID 占位字段，数据库层不添加对应的 `source_roots` 表，也不为该字段添加外键约束。

## 理由

1. **主规范 §8.1 未要求 S1 实现 SourceRoot 实体**：领域对象列表中不含此对象，S1 出口条件也未提及。
2. **严格按阶段推进**：`tasks.yaml` execution_contract 要求 `strict_phase_order: true`，提前在 S1 建 S3 的表违反阶段纪律。
3. **MVP 可用性**：S1 只需存储和查询已解析文档；根目录配置的运行时管理由 S3 负责。
4. **降低 S1 复杂度**：SourceRoot 的排除规则、扫描策略、状态管理属于业务逻辑，不应在 S1 存储基线中引入。

## 已知风险与约束

- **无 FK 约束**：在 S3 之前，`source_root_id` 值的合法性由调用方（脚本、测试 fixture）自行保证。
- **UUID 格式仍受约束**：`documents` 表的 `source_root_id` 有 UUID 格式 CHECK 约束（migration 0001/0005），不会存入格式非法的值。
- **S2 兼容**：S2（解析器与切片器）可继续使用占位 UUID 作为 `source_root_id`，无需等待 S3。
- **S3 补救选项**：S3 建立 `source_roots` 表后，可选择通过新 migration 追加外键约束，或维持当前无 FK 的宽松设计。

## 影响

- S1 所有测试继续使用任意合法 UUID 作为 `source_root_id`（当前 `_new_document()` fixture 已如此）。
- S3 必须在 `source_roots` 表建立后，维护 `source_root_id` 的引用完整性。
- 若 S3 决定追加 FK，需新 migration；若不追加，需在 ADR-S3 中记录权衡。
