# OpenDocs Codex 启动提示词 v1.4

> 本文件只负责把代理带到正确起点。
> 完整规则裁决链、职责矩阵与默认施工法则只看 `docs/specs/OpenDocs_工程实施主规范_v1.0.md`。

## 1. 必须读取的文件

权威文件：

1. `docs/specs/OpenDocs_工程实施主规范_v1.0.md`
2. `docs/acceptance/tasks.yaml`
3. `docs/acceptance/acceptance_cases.md`
4. `docs/prompts/codex_operator_prompt.md`
5. `AGENTS.md`

可选桥梁文件：

- `docs/guides/OpenDocs_Codex_阶段提示词清单.md`
- `docs/guides/OpenDocs_Codex_从零到一小白执行手册.md`

桥梁文件只做执行引导，不得覆盖权威文件。

## 2. 任务判断规则

- 如果人类明确要求重写治理文档、收敛规范、修正文档冲突或重写桥梁文件，按“治理重构”处理。
- 治理重构不得修改任何阶段 `status`，也不得声称任何产品阶段已完成。
- 否则，当前阶段默认取 `tasks.yaml` 中最早一个 `status != completed` 的阶段；如人类明确指定阶段，以人类指定为准。
- 若是阶段施工，必须同时读取当前阶段的 `implementation_basis`、`legacy_code_policy`、`delivery_mode`；这三个字段是正式施工信号，不是说明性注释。

## 3. 第一轮必须输出什么

第一轮只输出以下内容，不直接开始实现：

1. 当前任务类型：阶段施工，还是治理重构。
2. 当前阶段，或本次治理重构的目标与完成条件。
3. 计划修改的文件。
4. 将运行的测试与验证命令。
5. 迁移策略判断：
   - 本次采用“旁路新建切换”还是“低风险直接替换”
   - 新旧实现边界
   - 入口切换点
   - 旧实现收口范围与时机

如果当前阶段 `delivery_mode = refactor_against_legacy`（当前应为 `S0-S5`），第一轮还必须补充：

- 明确说明“该阶段已有旧实现时，将以新规范为唯一依据，旧实现仅作参考并视情况破坏式重构”
- 旧实现处理策略：哪些复用、哪些旁路新建、哪些切换入口后收口
- 不得把“现状已经能跑”当成保留旧实现或放宽规范的理由

如果是治理重构，第一轮还必须补充：

- 当前发现的重复点、冲突点或缺漏点
- 若会最小修正 `docs/adr/` 或 `docs/architecture/overview.md`，明确这些旁支文件只做引用或术语修正
- 本次不会修改阶段 `status` 的明确承诺

## 4. 可直接复制的启动提示词

````text
你是 OpenDocs 项目的施工代理。

先完整读取以下权威文件，并严格按职责边界协同工作：
1. docs/specs/OpenDocs_工程实施主规范_v1.0.md
2. docs/acceptance/tasks.yaml
3. docs/acceptance/acceptance_cases.md
4. docs/prompts/codex_operator_prompt.md
5. AGENTS.md

如果同时提供了桥梁文件，它们只作为执行桥梁，不是规则主定义处：
- docs/guides/OpenDocs_Codex_阶段提示词清单.md
- docs/guides/OpenDocs_Codex_从零到一小白执行手册.md

任务判断：
- 如果人类明确要求重写治理文档、收敛规范、修正文档冲突或重写桥梁文件，按“治理重构”处理。
- 否则，当前阶段 = tasks.yaml 中最早一个 status != completed 的阶段；如果人类明确指定阶段，以人类指定为准。
- 若是阶段施工，必须读取当前阶段的 implementation_basis、legacy_code_policy、delivery_mode，并按这些字段决定施工口径。

读取后，第一轮只输出：
1. 当前任务类型；
2. 当前阶段，或本次治理重构的目标与完成条件；
3. 计划修改的文件；
4. 将运行的测试与验证命令；
5. 迁移策略判断与切换计划。

如果当前阶段的 delivery_mode = refactor_against_legacy（当前应为 S0-S5），第一轮还必须补充：
- 该阶段已有旧实现时，将以新规范为唯一依据，旧实现仅作参考并视情况破坏式重构；
- 旧实现中哪些复用、哪些旁路新建、哪些切换入口后收口；
- 不得把“现状已经能跑”当成保留旧实现或放宽规范的理由。

如果是治理重构，还必须补充：
- 当前发现的重复点、冲突点或缺漏点；
- 如涉及 docs/adr/ 或 docs/architecture/overview.md，只允许做最小引用或术语修正；
- 本次不会修改任何阶段 status；
- 这次验证只按文档治理要求执行，不冒充阶段测试通过。

第一轮不要直接开始实现。
````
