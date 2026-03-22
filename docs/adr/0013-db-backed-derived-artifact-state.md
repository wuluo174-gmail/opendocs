# ADR-0013: DB-backed derived artifact state for dense index consistency

- 状态：Accepted
- 日期：2026-03-20
- 阶段：S3 / S4 收口

## 背景

OpenDocs 的 dense 检索使用 HNSW 作为派生索引，但此前一致性主要依赖以下信号：

1. 磁盘上的 HNSW 主文件
2. `.hnsw_labels` sidecar
3. `.hnsw_dirty` dirty flag
4. 调用方是否记得在补偿或启动修复时传入正确的 embedder

这种设计有两个问题：

- **权威状态不在数据库**：SQLite 明确是文档与 chunk 的 source of truth，但 dense 索引是否可用、是否过期、是否需要重建，并没有落在 SQLite 中统一表达。
- **恢复责任分散**：`IndexBuilder`、`IndexService`、`SearchService` 都可能触发 HNSW 修复，容易出现“某条路径忘记传 embedder”或“文件状态被清掉但真实 dense 索引已经退化”的问题。

另外，S3/S4 收口时还发现一个更深层的一致性问题：

- 文档重建时，SQLite 中旧 chunk 会被删除，但 HNSW 中旧 label 可能保留，导致 dense 通道返回陈旧片段。

本项目当前仍处于开发阶段，**没有历史用户数据负担**，因此可以直接把 dense 派生索引的一致性规则升级为更严格的 DB-backed 方案，而不必为旧行为长期兼容。

## 决策

接受 **DB-backed derived artifact state** 方案，把 dense HNSW 视为 SQLite 驱动的派生工件，而不是自描述的半权威存储。

1. 新增 SQLite 表 `index_artifacts`
   - 当前先管理一个工件：`dense_hnsw`
   - 记录：
     - `artifact_name`
     - `status`：`stale / ready / building / failed`
     - `artifact_path`
     - `embedder_model`
     - `embedder_dim`
     - `embedder_signature`
     - `last_error`
     - `last_reason`
     - `last_built_at`
     - `updated_at`

2. 明确权威边界
   - `documents / chunks` 是内容事实的权威来源
   - `index_artifacts` 是派生索引状态的权威来源
   - HNSW 文件、labels 文件、dirty flag 仅是派生工件与辅助信号，**不是权威状态**

3. 统一失效规则
   - 以下任一情况都必须把 `dense_hnsw` 视为 `stale`：
     - 文档新增、修改、删除导致 chunk 集合变化
     - HNSW 文件缺失
     - labels sidecar 缺失
     - dirty flag 存在
     - `artifact_path` 变化
     - `embedder_model` 变化
     - `embedder_dim` 变化
     - `embedder_signature` 变化
     - 启动健康检查发现索引文件不兼容或损坏

4. 统一修复责任
   - `HnswManager` 作为 dense 工件状态机的唯一入口
   - 启动修复、补偿重建、失败记录、成功回写都通过 `HnswManager` 更新 `index_artifacts`
   - 调用方不再自行定义“何时算修好”

5. 统一状态迁移
   - 开始重建前：写 `building`
   - 重建成功后：写 `ready`
   - 重建失败后：写 `failed`，并保留 `dirty flag`
   - 文档/chunk 变化的事务中：先写 `stale`，事务提交后再尝试增量或全量修复

6. 禁止无意的 dense 退化
   - 在正常 dense 链路中，不允许因为忘记传 embedder 而悄悄清掉 dirty 并保留零向量索引
   - 若缺少 embedder，应保留 `failed/stale` 状态并显式记录错误

7. 对旧开发期工件的处理
   - 由于当前没有历史用户数据，缺少 `index_artifacts` 记录的旧 HNSW 文件直接视为 `stale`
   - 下次启动或索引时按当前 embedder 规则重建，不保留长期兼容分支

## 理由

1. **符合“数据从哪里来”的根因治理**
   - 文档事实来自 SQLite
   - 派生索引是否可信也必须来自 SQLite 中的显式状态，而不是磁盘猜测

2. **降低调用点漂移风险**
   - 把规则集中到 `HnswManager` 后，不必依赖每个调用方都记得传 embedder、记得何时清 dirty、记得何时重建

3. **更适合开发阶段**
   - 当前没有历史用户数据，最合理的策略是直接升级到一致性更强的方案，而不是保留脆弱兼容路径

4. **便于后续扩展**
   - 将来若增加其他派生工件（例如 rerank cache、QA evidence cache、classifier cache），可以复用同一模式纳入 `index_artifacts`

## 被否决的方案

| 方案 | 否决原因 |
|------|----------|
| 继续仅依赖 `.hnsw_dirty` | 只能表达“某次写失败”，不能表达 embedder 漂移、路径漂移、签名漂移 |
| 只增强 `.hnsw_labels` sidecar | sidecar 仍是磁盘启发式，不是 SQLite 权威状态 |
| 在每个调用点分别判断并补偿 | 规则分散，容易重复犯“忘记传 embedder / 清错状态”的同类错误 |
| 保留零向量 fallback 作为默认补偿 | 会把 dense 通道悄悄降级成不可感知的伪可用状态 |

## 影响

- 需要 schema 迁移 `0004_index_artifacts.sql`
- dense 一致性判断从“文件启发式”升级为“DB 状态 + 工件健康检查”
- 启动时可能更积极地触发 HNSW 重建，这是有意设计
- 文档重建/删除时，dense 索引必须同步处理旧 chunk 的 HNSW 删除，不能只删 SQLite
- 后续若替换 embedder 或修改特征提取规则，必须同步更新 `embedder_signature` 语义

## 实施约束

后续所有 dense 相关代码必须遵守以下规则：

1. 不得把 HNSW 文件当作事实源
2. 不得仅靠 dirty flag 判定 dense 是否健康
3. 不得在 embedder 缺失时静默清理错误状态
4. 不得在删除/重建 chunk 后遗漏 HNSW 旧 label 清理
5. 若修改 dense embedder 算法、维度或签名规则，必须更新代码并评估是否需要新增 ADR
