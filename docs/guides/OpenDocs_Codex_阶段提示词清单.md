# OpenDocs Codex 执行桥梁模板 v4.1

用途：把权威文件里的规则，快速转成一轮可执行的 Codex 对话。

本文件是桥梁文件，不是规则主定义处。完整规则裁决链、职责矩阵与默认施工法则看主规范；输出纪律看 `AGENTS.md`。

---

## 0. 使用前先记住

- 阶段信息、`test_commands`、`exit_criteria`、`acceptance_refs` 只从 `docs/acceptance/tasks.yaml` 当前阶段读取。
- 当前阶段的 `implementation_basis`、`legacy_code_policy`、`delivery_mode` 也只从 `docs/acceptance/tasks.yaml` 当前阶段读取。
- 最终通过/失败只看 `docs/acceptance/acceptance_cases.md`。
- 桥梁文件不手工维护阶段明细，不复制完整规则链。
- 桥梁文件只给执行模板，不复写主规范、阶段门禁或验收正文。
- 关于助手目标水平与记忆目标，只转译主规范：系统应主动承担扫描、编码、整合、规划等元工作，不应把记忆维护变成用户手工任务。

---

## 1. 阶段施工模板

把下面这段发给 Codex，再把 `{...}` 换成当前事实：

````text
先完整读取 6 个权威文件：
1. docs/specs/OpenDocs_工程实施主规范_v1.0.md
2. docs/acceptance/tasks.yaml
3. docs/acceptance/acceptance_cases.md
4. docs/prompts/codex_operator_prompt.md
5. AGENTS.md
6. CLAUDE.md

当前任务类型：阶段施工
当前阶段：{S0}

要求：
- 只处理当前阶段，不得进入下一阶段；
- 当前阶段目标、test_commands、exit_criteria、acceptance_refs、implementation_basis、legacy_code_policy、delivery_mode 直接从 tasks.yaml 当前阶段读取；
- 若当前阶段涉及记忆或助手编排，不要把能力做成“用户手工保存记忆、手工整理偏好、手工拼上下文”的被动流程；
- 输出：
  1. 当前阶段；
  2. 当前阶段目标与出口条件；
  3. 计划修改的文件；
  4. 将运行的测试与验证命令；
  5. 本次采用“旁路新建切换”还是“低风险直接替换”，以及理由、边界、切换点、收口时机；
````

如果当前阶段 `delivery_mode = refactor_against_legacy`，再额外追加这一段：

````text
补充要求：
- 该阶段已有旧实现时，以新规范为唯一依据，旧实现仅作参考；
- 不得因为旧实现已经能跑、已经精密可用，就反向放宽规范；
- 还必须说明：哪些旧实现复用、哪些旁路新建、哪些切换入口后收口。
````

---

## 2. 治理重构模板

把下面这段发给 Codex，再把 `{...}` 换成当前事实：

````text
先完整读取 6 个权威文件：
1. docs/specs/OpenDocs_工程实施主规范_v1.0.md
2. docs/acceptance/tasks.yaml
3. docs/acceptance/acceptance_cases.md
4. docs/prompts/codex_operator_prompt.md
5. AGENTS.md
6. CLAUDE.md

当前任务类型：治理重构
治理目标：{例如：收敛规范、删除重复、修正冲突、补全交叉引用}

要求：
- 本次工作不计入 S0-S11 阶段完成；
- 不得修改任何阶段 status；
- 不得声称任何产品阶段已完成；
- 如需修正 docs/adr/ 或 docs/architecture/overview.md，只允许做最小引用或术语修正；
- 输出：
  1. 本次治理重构目标与完成条件；
  2. 当前发现的重复点、冲突点、缺漏点；
  3. 计划修改的文件；
  4. 将运行的验证命令；
  5. 本次采用“低风险直接替换”还是“旁路新建切换”，以及理由；
  6. 不会修改任何阶段 status 的明确承诺；
````

---

## 3. 执行追加模板

计划确认后，再发这一段：

````text
按刚才确认的计划开始实施。

要求：
- 小步修改；
- 实际运行验证命令；
- 阶段施工时直接使用 tasks.yaml 当前阶段的 test_commands；
- 如果当前阶段 delivery_mode = refactor_against_legacy，执行中始终按“规范主导、旧实现仅作参考”口径推进；
- 治理重构时执行交叉引用检查、YAML 解析检查、重复/冲突扫描与差异复核；
- 若验证失败，只修当前失败的最小原因；
- 在出口条件或治理完成条件满足前，不得宣布完成。
````

---

## 4. 阻塞模板

卡住时发这一段：

````text
不要扩大范围，不要跳阶段。
请只处理当前任务的最小阻塞问题，并按下面格式回答：
1. 最小阻塞点；
2. 根因；
3. 最小安全修复；
4. 修复后立即重跑哪些命令；
5. 本次仍采用哪种迁移方式，为什么。
````

---

## 5. 最后只认什么

- 规则只认权威文件。
- 阶段施工只认 `tasks.yaml` 当前阶段与真实命令输出。
- 治理重构只认文档差异和治理验证结果。
- 正常情况下，用户不该靠手工整理记忆来让系统变聪明。
