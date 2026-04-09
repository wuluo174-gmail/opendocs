# OpenDocs 工程实施主规范（PRD + SRS + SAD）v1.0

> 本文件是 OpenDocs 的唯一产品与系统总规范。
> 它定义产品目标、系统边界、锁定技术决策、数据模型、功能需求、服务契约、安全红线与默认值。
> 它不再重复阶段门禁、完整验收用例或代理启动提示词。

---

## 0. 文档控制

### 0.1 文档信息

- 项目名称：OpenDocs
- 文档名称：OpenDocs 工程实施主规范
- 文档版本：v1.0
- 文档状态：Baseline
- 更新时间：2026-04-09
- 目标读者：
  - 产品负责人
  - 架构师
  - AI 施工代理
  - 测试与验收人员
  - 本地部署人员

### 0.2 本文件负责什么

本文件是 OpenDocs 的唯一完整总规范，负责定义：

- 产品定义、系统边界与核心原则
- 规则裁决顺序与治理文件职责矩阵
- 遗留实现改造的默认施工法则
- 锁定技术栈、架构基线、基础对象链、数据模型与系统不变量
- `FR-001 ~ FR-016`
- `NFR-001 ~ NFR-023`
- 应用服务契约、UI 边界、全局术语与默认值

本文件不负责定义：

- 阶段排序、阶段 `status`、阶段门禁、阶段测试命令：看 `docs/acceptance/tasks.yaml`
- 最终通过/失败判定、`TC-001 ~ TC-021`、验收报告契约：看 `docs/acceptance/acceptance_cases.md`
- 代理启动提示词：看 `docs/prompts/codex_operator_prompt.md`
- 仓库协作纪律、汇报要求与阻塞格式：看 `AGENTS.md`
- 桥梁模板与非开发者操作说明：看 `docs/guides/`

### 0.3 规则裁决顺序

规则裁决顺序从高到低：

1. `docs/specs/OpenDocs_工程实施主规范_v1.0.md`
2. `docs/acceptance/tasks.yaml`
3. `docs/acceptance/acceptance_cases.md`
4. `docs/prompts/codex_operator_prompt.md`

例外：

- 最终通过/失败判定与可执行验收行为以 `docs/acceptance/acceptance_cases.md` 为准。
- 阶段排序与阶段门禁以 `docs/acceptance/tasks.yaml` 为准。
- `AGENTS.md` 是仓库级持续纪律文件；若与上述裁决链冲突，以上述裁决链及其例外为准；若仅与 `docs/prompts/codex_operator_prompt.md` 的施工提示、输出格式或操作纪律冲突，以 `AGENTS.md` 为准。

本规则链是唯一完整主定义处；其他文件只能引用，不重复抄写整段裁决链。

### 0.4 治理文件职责矩阵

| 文件 | 类别 | 主责 | 是否为规则主定义处 |
| --- | --- | --- | --- |
| `docs/specs/OpenDocs_工程实施主规范_v1.0.md` | 权威文件 | 产品定义、系统架构、红线、默认施工法则、文件职责矩阵 | 是 |
| `docs/acceptance/tasks.yaml` | 权威文件 | 阶段排序、阶段目标、`test_commands`、出口条件、阶段 `status` | 是 |
| `docs/acceptance/acceptance_cases.md` | 权威文件 | 最终通过/失败判定、`TC-001 ~ TC-021`、验收报告契约 | 是 |
| `docs/prompts/codex_operator_prompt.md` | 权威文件 | 启动代理并把其带到正确起点 | 是，但只定义启动方式 |
| `AGENTS.md` | 权威文件 | 仓库纪律、输出要求、阻塞格式与汇报要求 | 是，但只定义仓库级纪律 |
| `docs/guides/OpenDocs_Codex_阶段提示词清单.md` | 桥梁文件 | 把权威文件翻译成可复制的执行模板 | 否 |
| `docs/guides/OpenDocs_Codex_从零到一小白执行手册.md` | 桥梁文件 | 给非开发者提供操作说明 | 否 |

补充说明：

- 桥梁文件只能引用权威文件，不能覆盖权威文件。
- “仓库治理重构”用于收敛规范、桥梁文件与交叉引用；它不改变阶段 `status`，也不构成阶段通过证据。
- 对 `tasks.yaml` 中 `delivery_mode=refactor_against_legacy` 的阶段，当前实现只作参考，不构成规范例外。
- 本矩阵是唯一完整职责定义处；其他文件只做短引用。

### 0.5 一句话定义

OpenDocs 是一个运行在个人电脑上的本地优先 AI 文档助理，专门用于扫描、索引、检索、问答、摘要、分类、归档、生成与审计文本类工作文档，并要求所有事实性输出都可回溯到文档证据。

---

## 1. 产品定义与范围

### 1.1 产品目标

OpenDocs 要解决的问题不是“文件看不见”，而是“文件太多、命名混乱、跨项目混放、内容难复用、事实难核验”。MVP 必须完成以下闭环：

1. 找得到：用户能用自然语言找到目标文档和证据片段。
2. 问得准：系统能给出带引用的事实性回答；证据不足时明确拒答。
3. 理得清：系统能基于内容证据给出分类、标签和归档建议，并在确认后安全执行。
4. 写得出：系统能基于历史文档生成有引用的草稿。
5. 可复核：关键操作有预览、确认、审计与回滚。

### 1.2 目标用户

1. 办公人员：周报、月报、会议纪要、制度材料、合同交付文档。
2. 研究人员：研究笔记、阶段报告、实验记录、论文相关材料。
3. 顾问与自由职业者：客户资料、交付件、报价、复盘文档。

### 1.3 核心 Jobs To Be Done

- “帮我找到某项目上个月的进度报告，并给我证据。”
- “汇总最近三个月会议纪要里的决策、风险和待办。”
- “把桌面上和 A 项目有关的文档整理出来，先给我看方案，再执行归档。”
- “基于最近四周周报生成一份月报草稿，并附上引用。”

### 1.4 助手目标水平与用户分工

OpenDocs 的目标不是“被动回答问题的聊天助手”，而是“主动型、半自治、受控执行的个人知识工作代理”。

- 用户主要给出目标、审核高风险动作、处理少量歧义与纠偏，不应承担大部分整理、归档、记忆维护和上下文拼装工作。
- 系统应主动完成扫描、解析、索引、检索、证据构造、记忆编码、后台整合、分类规划、草稿生成与状态延续。
- 正常工作流中，不应要求用户手动保存记忆、手动整理偏好、手动维护项目状态，或反复重述近期任务上下文。
- 用户的主要介入点只包括：确认 `move / rename / create / save_output` 等高风险写操作，处理证据冲突、路径冲突和少量记忆纠偏。
- 记忆管理页与人工修正入口属于兜底与审计能力，不应成为让系统“变聪明”的主工作流。

### 1.5 MVP In Scope

- 文档源配置、递归扫描、排除规则
- `.txt`、`.md`、`.docx`、文字层 `.pdf` 解析
- 全量索引、增量索引、重建索引
- 混合搜索：关键词 + 语义召回 + 过滤器
- 带引用的 RAG 问答
- 单文档摘要、多文档摘要、洞察提取
- 内容驱动分类与归档规划
- 模板生成与自由生成
- `M0 / M1 / M2` 记忆体系
- 模型路由、隐私模式、审计、回滚

### 1.6 MVP Out of Scope

- OCR
- 图片理解
- 音视频转写
- 网页抓取
- 多人协同审批
- 默认删除文件
- 复杂图数据库和企业级知识中台
- 通用电脑控制或浏览器自动化

### 1.7 成功定义

当以下条件同时成立时，MVP 才算成立：

- 在 1 万文档量级上具备稳定索引与增量更新
- 搜索、问答、摘要、分类、归档、生成、记忆、审计全链路可运行
- 事实性回答默认附引用
- 文件系统与用户输出写操作具备预览、确认、审计和最近一次批量回滚
- 受审计的内部记忆写入按本规范的记忆规则执行
- 用户不需手工维护记忆或重复整理上下文，系统能自动沉淀任务理解、偏好模式与状态快照
- `Local-Only` 模式下外发请求为 0
- 自动化验收与人工抽查结论一致

---

## 2. 核心原则与安全红线

### 2.1 核心原则

1. 本地优先：默认优先使用本地存储、本地索引、本地模型或本地 embedding。
2. 证据优先：事实性输出必须建立在文档证据之上。
3. 内容语义优先：索引、检索、分类、归档、生成的主信号来自文档内容，不是文件名或路径。
4. 审计优先：高风险动作必须可查询、可复盘。
5. 默认保守：证据不足时拒答，归类不清时待确认，路径冲突时停止。
6. 先新后旧：改造不可信旧实现时，默认先在旁边建立符合现规范的新实现，再切换入口并收口旧实现。

### 2.2 不可违反的红线

- 不得默认实现文件删除；本规范中的 `delete` 指文件系统删除，不等于 `memory_delete`
- 不得在无确认情况下执行 `move / rename / create`
- 不得让 UI 直接访问数据库、文件系统或 Provider
- 不得让记忆覆盖文档证据
- 不得把原始聊天记录原样持久化为 `M1/M2`
- 不得输出无引用的事实性结论
- 证据不足必须拒答
- 不得把统计型语义 fallback 静默伪装成正常 AI 理解
- 不得把分类/归档退化成只看文件名、路径、时间的规则系统
- 不得在 `Local-Only` 模式下发起外网请求
- 不得把密钥写入日志、明文配置或提交到仓库

### 2.3 遗留实现改造策略

- OpenDocs 当前仍处于初版开发阶段：无线上用户、无历史业务数据、无兼容承诺。后续开发允许并应当通过破坏式不兼容重构，把实现收回到当前规范与产品功能意图。
- 当前仓库中已经存在的代码、测试、脚本、阶段报告和其他旧产物，都只能当参考素材，不是实施基线。
- 即使某段旧实现已经精密可用，也不得据此放松规范、降低阶段门禁，或把实现现状反向写回规范。
- `S0 ~ S5` 已存在不同程度的旧实现沉淀；这些阶段默认按“待评估遗留实现”处理。AI 开发者必须先判断哪些可复用、哪些必须旁路新建、哪些必须切换入口后再收口旧实现。
- 对跨模块、跨阶段、核心数据流、核心服务边界相关的旧实现，默认采用“旁路新建 -> 对齐契约与测试 -> 切换入口 -> 验证通过 -> 收口旧实现”。
- 只有当前阶段内低风险、孤立、无复用价值的旧文件，才允许直接替换或删除；执行前必须说明为什么不需要双轨切换。
- 不得在旧泥潭里持续补丁式扩写，也不得为了保留旧路径写长期兼容胶水。
- 阶段是否完成只看 `tasks.yaml` 的阶段门禁与实际验证证据；治理重构不改变任何阶段 `status`。

### 2.4 关键术语

- 文档助理：OpenDocs 的产品定位，不是“带搜索框的文件管理器”。
- 语义模式：检索与分类所依赖的正常 embedding/语义表示模式。
- 统计 fallback：只有显式启用时才允许的降级模式，必须可见、可审计。
- 权威文件：在各自职责范围内具有规则裁决权的文件。
- 桥梁文件：把权威文件转译成执行模板或非开发者说明的辅助文件。
- 旁路新建切换：先在旧实现旁边建立新实现，对齐契约与测试后切换入口，再收口旧实现。
- 低风险直接替换：仅对当前阶段内低风险、孤立、无复用价值文件进行的直接替换或删除。
- 待评估遗留实现：当前仓库中已存在、但是否保留必须重新按现规范和产品功能意图评估的旧实现；它不是规则来源。
- 旧实现收口：在新入口稳定后，删除、封存或停止引用旧实现。
- `SourceRoot`：受控文档源根目录及其默认策略的持久化对象。
- `ScanRun`：一次扫描或增量扫描的结构化运行记录，是扫描统计与审计追踪的桥接对象。
- `IndexArtifact`：由源数据派生出的索引工件状态对象；它只表达派生工件状态，不与源数据混权。
- 文件删除：文件系统层面的 `delete`；默认无入口，不包含 `memory_delete`
- 文件系统与用户输出写操作：`move / rename / create / save_output` 一类会改变用户可见文件结果的动作。
- 受审计的内部记忆写入：`memory_encode`、`memory_consolidate`、`memory_promote` 及其状态迁移；它们属于系统内部受控写入，不属于用户可见写操作。

---

## 3. 锁定技术决策

### 3.1 锁定技术栈

| 领域 | 基线 |
| --- | --- |
| 语言 | Python 3.11 |
| 桌面 UI | PySide6 |
| 数据校验 | Pydantic v2 |
| 数据库 | SQLite 3 + FTS5 |
| ORM | SQLAlchemy 2.x |
| 向量索引 | hnswlib |
| 文件监听 | watchdog |
| 文档解析 | `.txt` 内置读取、`.md` Markdown 文本解析、`.docx` python-docx、`.pdf` PyMuPDF 优先 / pypdf 降级 |
| 模板 | Jinja2 |
| 测试 | pytest、pytest-qt、pytest-cov |
| 打包 | PyInstaller |
| 配置 | TOML + env |
| 密钥存储 | keyring |

### 3.2 语义表示策略

- 必须存在可替换的 embedding/语义表示适配层。
- `Local-Only` 模式优先本地 embedding；`Hybrid / Cloud-Assisted` 可按策略切换到云端 embedding。
- 统计型语义表示只允许作为显式降级模式，不得伪装成正常 AI 理解。
- 检索、分类、问答、生成使用的语义模式必须在运行状态、日志或审计中可见。

### 3.3 架构风格

- 架构采用模块化单体（modular monolith）。
- 不采用微服务，不引入与 MVP 无关的大型框架。
- 各业务模块共享同一套解析、chunk、语义表示与引用结构，不允许为单一功能各造一套“理解逻辑”。

### 3.4 检索策略

- 默认采用混合检索：FTS5 + dense retrieval + 规则化过滤 + 分数融合。
- 必须返回可引用证据，不能只返回标题或路径。
- 文件名、目录、时间只属于辅助过滤信号，不构成内容理解本身。

---

## 4. 系统上下文与总体架构

### 4.1 外部上下文

- 本地文件系统
- 本地模型与 embedding 运行环境
- 云端模型提供方 API
- 系统密钥管理器
- 用户桌面操作系统

### 4.2 内部组件

1. **Desktop UI**
   - 展示配置、搜索、问答、归档预览、生成、记忆管理、审计与回滚。
2. **Application Service Layer**
   - 统一业务编排入口；其中 `SourceService` 负责 `SourceRoot` 与 `ScanRun`，`IndexService` 负责索引流程与 `IndexArtifact`。
3. **Parser Registry**
   - 识别文件类型并输出统一 `ParsedDocument`。
4. **Indexer**
   - 扫描、切片、哈希、索引入库、向量入库、派生索引状态维护。
5. **Retrieval Engine**
   - 混合召回、融合排序、过滤、证据构造。
6. **QA / Insight Engine**
   - 问答、摘要、洞察、冲突检测、引用校验。
7. **Classification & Archive Planner**
   - 基于内容证据输出分类、路径建议、风险与计划。
8. **Generation Engine**
   - 模板生成、自由生成、引用插入、保存前预览。
9. **TaskEvent Service**
   - `TaskEvent` 的唯一写入口；负责结构化事件持久化与可追溯性校验。
10. **Memory Service**
   - 管理 `M0` 运行时状态、`M1/M2` 编码、整合、召回强化、衰减与冲突治理。
11. **Provider Service**
   - 路由 LLM 与 embedding Provider，管理网络模式与外发最小化。
12. **Audit & Rollback Service**
   - 审计记录、审计查询、最近一次批量回滚。
13. **Config & Security Service**
   - 配置、密钥、敏感信息策略与权限控制。

### 4.3 核心流程

#### A. 扫描与索引

1. 保存或更新 `SourceRoot` 与排除规则
2. 创建 `ScanRun`，分配 `trace_id`
3. 扫描器枚举文件
4. 解析器输出文本和元数据
5. 切片器输出结构与语义一致的 chunk
6. 生成语义表示
7. 写入 SQLite / FTS5 / HNSW
8. 更新 `IndexArtifact` 与当前语义模式状态
9. 记录审计与索引运行信息

#### B. 搜索与问答

1. 用户输入查询或问题
2. 检索引擎执行混合召回与过滤
3. 构造候选证据集合
4. QA 编排器生成候选结果
5. 引用校验器与冲突检测器做二次校验
6. 返回答案、引用、冲突提示或证据不足拒答

#### C. 分类与归档

1. 读取目标文档集及其内容证据
2. 输出分类、标签、置信度、内容依据、建议目标路径
3. 生成 `FileOperationPlan`
4. UI 展示预览、风险与差异
5. 用户确认后执行
6. 写审计并保留最近一次批量回滚点

#### D. 生成与保存

1. 选择模板或自由生成
2. 检索上下文证据
3. 生成草稿并插入引用
4. 用户编辑
5. 用户确认保存
6. 写审计与 `TaskEvent`

---

## 5. 数据模型与系统不变量

### 5.0 基础对象链

OpenDocs 的基础对象链必须保持单向可追溯：

`SourceRoot -> Document -> Chunk / KnowledgeItem -> TaskEvent -> MemoryItem`

补充要求：

- `ScanRun` 属于 `SourceRoot` 的运行记录对象，负责承接“这次扫描到底扫了什么、失败了什么、链路如何回查”。
- `IndexArtifact` 属于由 `Document / Chunk` 派生出的索引工件状态对象，负责承接“当前 dense 索引是否可用、是否过期、为何降级”。
- `FileOperationPlan` 属于受控写操作的计划对象，负责承接“预览、确认、执行、回滚”链路，不得被 UI 或脚本跳过。

### 5.A SourceRoot

`SourceRoot` 是文档来源的持久化根对象。它不是扫描脚本里的临时参数，而是所有 `Document` 与 `ScanRun` 的上游锚点。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `source_root_id` | UUID | 根目录唯一 ID |
| `path` | TEXT | 根目录绝对路径 |
| `display_root` | TEXT | 面向 UI / 审计的稳定显示根名 |
| `label` | TEXT | 用户可读标签，可空 |
| `exclude_rules_json` | JSON | 排除规则 |
| `default_category` | TEXT | 根目录默认分类，可空 |
| `default_tags_json` | JSON | 根目录默认标签 |
| `default_sensitivity` | TEXT | 默认敏感等级，可空 |
| `source_config_rev` | INTEGER | 根目录配置版本，单调递增 |
| `recursive` | BOOLEAN | 是否递归扫描 |
| `is_active` | BOOLEAN | 是否启用 |
| `created_at` | DATETIME | 创建时间 |
| `updated_at` | DATETIME | 最近更新时间 |

### 5.B ScanRun

`ScanRun` 是一次扫描或增量扫描的结构化运行记录。扫描统计、失败摘要、链路追踪与审计回查都以它为桥接对象。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `scan_run_id` | UUID | 扫描运行 ID |
| `source_root_id` | UUID | 所属根目录 ID |
| `started_at` | DATETIME | 开始时间 |
| `finished_at` | DATETIME | 结束时间，可空 |
| `status` | TEXT | `running / completed / failed` |
| `included_count` | INTEGER | 纳入处理文件数 |
| `excluded_count` | INTEGER | 被排除文件数 |
| `unsupported_count` | INTEGER | 不支持文件数 |
| `failed_count` | INTEGER | 失败文件数 |
| `error_summary_json` | JSON | 失败摘要与典型原因 |
| `trace_id` | TEXT | 与审计、索引、回放链路共享的追踪 ID |

### 5.C IndexArtifact

`IndexArtifact` 是派生索引工件状态，不保存源事实本身。它只回答“当前工件是否可用、为何失效、由什么语义配置构建”。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `artifact_name` | TEXT | 工件名，如 `dense_hnsw` |
| `status` | TEXT | `stale / ready / building / failed` |
| `artifact_path` | TEXT | 工件路径 |
| `embedder_model` | TEXT | 语义表示模型或方法名 |
| `embedder_dim` | INTEGER | 向量维度 |
| `embedder_signature` | TEXT | 用于判定兼容性的签名 |
| `last_error` | TEXT | 最近失败错误，可空 |
| `last_reason` | TEXT | 最近状态变化原因，可空 |
| `last_built_at` | DATETIME | 最近成功构建时间，可空 |
| `updated_at` | DATETIME | 最近更新时间 |

### 5.1 Document

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `doc_id` | UUID | 文档唯一 ID |
| `path` | TEXT | 当前绝对路径 |
| `relative_path` | TEXT | 相对根目录路径 |
| `display_path` | TEXT | 面向 UI / 审计的稳定显示路径 |
| `directory_path` | TEXT | 当前目录绝对路径 |
| `relative_directory_path` | TEXT | 相对根目录目录路径 |
| `file_identity` | TEXT | 用于增量更新与重建幂等的稳定文件身份，可空 |
| `source_root_id` | UUID | 所属根目录 |
| `source_path` | TEXT | 初始来源路径 |
| `source_config_rev` | INTEGER | 写入时使用的源配置版本 |
| `hash_sha256` | TEXT | 内容哈希 |
| `title` | TEXT | 标题 |
| `file_type` | TEXT | `txt / md / docx / pdf` |
| `size_bytes` | INTEGER | 文件大小 |
| `created_at` | DATETIME | 创建时间 |
| `modified_at` | DATETIME | 修改时间 |
| `indexed_at` | DATETIME | 最近索引时间 |
| `parse_status` | TEXT | `success / partial / failed` |
| `category` | TEXT | 当前主分类 |
| `tags_json` | JSON | 标签列表 |
| `sensitivity` | TEXT | `public / internal / sensitive` |
| `is_deleted_from_fs` | BOOLEAN | 文件是否已从文件系统删除 |

### 5.2 Chunk

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `chunk_id` | UUID | 片段 ID |
| `doc_id` | UUID | 来源文档 ID |
| `chunk_index` | INTEGER | 文档内顺序 |
| `text` | TEXT | 片段文本 |
| `char_start` | INTEGER | 起始字符偏移 |
| `char_end` | INTEGER | 结束字符偏移 |
| `page_no` | INTEGER | PDF 页码，可空 |
| `paragraph_start` | INTEGER | 起始段落，可空 |
| `paragraph_end` | INTEGER | 结束段落，可空 |
| `heading_path` | TEXT | 标题路径，可空 |
| `token_estimate` | INTEGER | 估算 token 数 |
| `embedding_model` | TEXT | 使用的语义表示模型或方法 |
| `embedding_key` | TEXT | 向量索引键 |

### 5.3 KnowledgeItem

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `knowledge_id` | UUID | 知识条目 ID |
| `doc_id` | UUID | 来源文档 ID |
| `chunk_id` | UUID | 来源片段 ID |
| `summary` | TEXT | 条目摘要 |
| `entities_json` | JSON | 实体列表 |
| `topics_json` | JSON | 主题列表 |
| `confidence` | REAL | 抽取置信度 |

### 5.4 RelationEdge

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `edge_id` | UUID | 边 ID |
| `src_type` | TEXT | 源对象类型 |
| `src_id` | TEXT | 源对象 ID |
| `dst_type` | TEXT | 目标对象类型 |
| `dst_id` | TEXT | 目标对象 ID |
| `relation_type` | TEXT | `related_to / mentions / derived_from / same_project` 等 |
| `weight` | REAL | 关系权重 |
| `evidence_chunk_id` | UUID | 证据片段 ID |

### 5.5 TaskEvent 最小字段契约

`TaskEvent` 是跨阶段结构化任务事件的唯一持久化模型。它是 `M1/M2` 记忆编码与整合的上游事实载体。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `event_id` | UUID | 事件 ID |
| `trace_id` | TEXT | 链路 ID |
| `stage_id` | TEXT | 来源阶段，如 `S5 / S6 / S7` |
| `task_type` | TEXT | `qa / summary / archive_preview / archive_execute / archive_rollback / generation_save` 等 |
| `scope_type` | TEXT | `session / task / user` |
| `scope_id` | TEXT | 作用域 ID |
| `input_summary` | TEXT | 输入摘要 |
| `output_summary` | TEXT | 输出摘要 |
| `related_chunk_ids_json` | JSON | 相关 chunk 列表 |
| `evidence_refs_json` | JSON | 结构化引用列表 |
| `related_plan_id` | UUID | 关联的 `FileOperationPlan.plan_id`；仅归档预览/执行/回滚相关事件必填 |
| `artifact_ref` | TEXT | 关联产物路径或持久化位置 |
| `occurred_at` | DATETIME | 任务完成时间 |
| `persisted_at` | DATETIME | 事件落盘时间 |

### 5.6 MemoryItem

`M0` 只存在于运行时，不落盘，不进入 `MemoryItem` 表。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `memory_id` | UUID | 记忆 ID |
| `memory_type` | TEXT | `M1 / M2` |
| `memory_kind` | TEXT | `task_snapshot / retry_point / preference_pattern / workflow_hint` |
| `scope_type` | TEXT | `task / user` |
| `scope_id` | TEXT | 作用域 ID |
| `key` | TEXT | 记忆键 |
| `content` | TEXT | 结构化记忆摘要 |
| `source_event_ids_json` | JSON | 来源事件 ID 列表 |
| `evidence_refs_json` | JSON | 支撑证据引用列表 |
| `importance` | REAL | 重要性分数 |
| `confidence` | REAL | 编码或整合置信度 |
| `status` | TEXT | `active / expired / disabled / superseded` |
| `review_window_days` | INTEGER | `M1` 复审窗口天数 |
| `user_confirmed_count` | INTEGER | 用户显式确认或修正次数 |
| `last_user_confirmed_at` | DATETIME | 最近用户确认或修正时间 |
| `recall_count` | INTEGER | 被召回并采用的次数 |
| `last_recalled_at` | DATETIME | 最近召回时间 |
| `decay_score` | REAL | 当前衰减分数 |
| `promotion_state` | TEXT | `candidate / promoted` |
| `consolidated_from_json` | JSON | 被合并来源记忆 ID 列表 |
| `supersedes_memory_id` | UUID | 被替代旧记忆 ID |
| `updated_at` | DATETIME | 更新时间 |

### 5.7 FileOperationPlan

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `plan_id` | UUID | 计划 ID |
| `operation_type` | TEXT | `move / rename / create` |
| `status` | TEXT | `draft / approved / executed / rolled_back / failed` |
| `item_count` | INTEGER | 操作项数量 |
| `risk_level` | TEXT | `low / medium / high` |
| `preview_json` | JSON | 预览内容；必须包含逐项变更、原路径/目标路径、依据摘要、风险与回滚所需最小信息 |
| `approved_at` | DATETIME | 用户确认时间 |
| `executed_at` | DATETIME | 执行时间 |

### 5.8 AuditLog

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `audit_id` | UUID | 审计 ID |
| `timestamp` | DATETIME | 时间 |
| `actor` | TEXT | `user / system / model` |
| `operation` | TEXT | 操作类型 |
| `target_type` | TEXT | 如 `document / plan / memory / task_event / answer / source / search / provider_call / generation / index_run / rollback / artifact` |
| `target_id` | TEXT | 目标 ID |
| `result` | TEXT | `success / failure` |
| `detail_json` | JSON | 审计详情 |
| `trace_id` | TEXT | 链路 ID |

### 5.9 数据不变量

1. 所有事实性回答必须关联至少一个真实引用。
2. `Document.source_root_id` 与 `ScanRun.source_root_id` 只能引用真实存在的 `SourceRoot`。
3. `ScanRun` 只能描述一次真实扫描运行，不能拿来伪造批任务统计。
4. `IndexArtifact` 只表达派生工件状态；工件失效不得反向污染 `Document / Chunk` 的源事实。
5. 所有 `KnowledgeItem` 必须能回溯到 `Document + Chunk`。
6. `TaskEvent` 是结构化任务事件的唯一持久化模型与唯一上游事实载体。
7. `TaskEvent` 必须先落盘，`MemoryItem.source_event_ids_json` 才允许引用对应 `event_id`。
8. `M0` 不得以 `MemoryItem` 形式落盘。
9. 持久化 `MemoryItem.scope_type` 只允许 `task / user`，不得持久化 `session`。
10. `M1/M2` 只能来源于结构化事件、证据引用与编码结果，不得直接持久化原始聊天上下文。
11. `M2` 默认关闭；关闭时不得自动持久化偏好。
12. 低于阈值的偏好只能以 `memory_type=M2` + `promotion_state=candidate` 持久化，且不得参与正常召回。
13. `candidate / disabled / expired / superseded` 记忆不得参与正常召回。
14. 所有 `move / rename / create` 必须先生成 `FileOperationPlan`。
15. `FileOperationPlan.preview_json` 必须足以独立表达逐项预览、依据摘要、风险和最近一次批量回滚所需最小信息。
16. 归档预览、执行、回滚相关 `TaskEvent` 必须带 `related_plan_id`，且可追溯到真实 `FileOperationPlan.plan_id`。
17. 所有执行过的写操作必须有对应 `AuditLog`。
18. 最近一次批量回滚只覆盖文件系统与用户输出写操作；记忆纠偏通过 `disable / correct / delete` 处理。
19. 活跃 `Chunk` 必须具备可用语义表示，或在运行状态/日志/审计中明确标记为降级模式。
20. 当前语义模式与 `IndexArtifact` 状态必须可查询、可显示或可审计。

---

## 6. 功能需求

### FR-001 文档源配置与扫描

- 支持配置一个或多个 `SourceRoot`、排除规则和递归扫描。
- `SourceRoot` 必须持久化默认分类、标签、敏感等级与配置版本，不得退化成脚本临时参数。
- 扫描必须输出纳入、排除、失败统计，持久化 `ScanRun`，并记录审计。
- 单文件失败不得拖垮整个批任务。
- 不支持或损坏文件必须进入排除/失败清单，而不是悄悄丢失。

### FR-002 索引构建与增量更新

- 支持首次全量索引、监听式增量更新和手动重建。
- 索引必须同时刷新结构化 chunk 和语义表示。
- dense 派生索引状态必须通过 `IndexArtifact` 明确表达，而不是只靠磁盘文件是否存在来推断。
- 删除文件后，结果中不得继续返回已删除文档。
- 重建索引必须幂等，不得产生脏重复数据。
- 当前语义模式、降级状态与 `IndexArtifact` 状态必须可见、可查询、可审计。

### FR-003 混合智能搜索

- 实现 FTS5 + dense retrieval + 过滤器 + 分数融合。
- 返回结果必须包含标题、路径、摘要、时间、分数和引用定位。
- 对同义表达、中性命名、文件名缺少核心词的文档具备基本召回能力。
- 过滤器至少支持目录、分类、标签、文件类型、时间范围、敏感等级。

### FR-004 文档问答（RAG）

- 支持事实问答、对比、汇总、时间线等问题类型。
- 所有事实性回答默认附引用。
- 证据不足时必须拒答，不得猜。
- 证据冲突时必须展示冲突来源，不得硬凑单一结论。

### FR-005 摘要与洞察

- 支持单文档摘要、多文档汇总、决策/风险/待办提取。
- 每条关键结论必须能回溯到来源引用。
- 支持 Markdown 导出。
- 摘要/洞察完成后必须写入符合主规范 `TaskEvent` 最小字段契约的结构化事件。

### FR-006 分类与归档

- 分类主信号来自正文、chunk 证据、语义邻域和相关文档内容。
- 文件名、目录、时间、文件类型只允许作为辅助弱信号。
- 内容证据不足、证据冲突或置信度不足时必须进入待确认，而不是强行归档。
- 物理归档必须先预览，再确认，再执行，并支持最近一次批量回滚。
- 归档预览、执行、回滚都必须写入符合主规范的 `TaskEvent`；相关事件必须带 `related_plan_id`。

### FR-007 知识生成

- 支持模板生成与自由生成。
- 生成结果必须包含引用区块或尾注区块。
- 保存前必须允许编辑并要求确认。
- 保存后必须写入符合主规范 `TaskEvent` 最小字段契约的结构化事件。

### FR-008 记忆体系

- `M0` 为运行时会话状态，不落盘。
- 记忆目标是把交互沉淀为可复用的任务理解、偏好模式与状态快照，而不是存储原始对话全文。
- `M1` 为任务边界自动编码的结构化记忆，默认带衰减和 30 天复审/硬上限。
- `M2` 为长期偏好，默认关闭；只有开启后才允许自动晋升。
- 自动编码触发点至少包括：问答、摘要、归档预览/执行/回滚、生成保存。
- 自动编码输入必须来自已落盘 `TaskEvent`、操作摘要与证据引用；可由 LLM 驱动提炼出用户关注主题、偏好模式、任务状态快照等结构化结果。
- 启动时和空闲时必须执行后台整合：去重、合并、状态更新、升级判断；整合目标是把零散记忆收敛成更高密度的结构化记忆，而不是持续堆积条目。
- 默认不要求用户手动保存记忆、手动整理偏好或手动维护任务状态。

### FR-009 记忆与知识冲突处理

- 文档证据永远优先于记忆。
- 记忆冲突时必须明确提示“记忆可能陈旧或错误”。
- 用户必须能禁用、删除、修正冲突记忆，或用新记忆 `supersede` 旧记忆。
- 被禁用、过期、`superseded` 的旧记忆不得继续参与正常召回。

### FR-010 长上下文编排

- 在有限 token 预算下优先保留关键证据。
- 裁剪顺序必须先裁冗余历史、低置信记忆、重复证据，再裁非核心背景。
- 超预算时不得优先裁掉关键文档证据。

### FR-011 文件操作安全与回滚

- 允许的物理写操作只有 `create / rename / move`。
- 所有用户可见写操作都必须遵循“预览 -> 确认 -> 执行 -> 审计 -> 回滚”。
- `FileOperationPlan.preview_json` 至少要覆盖逐项变更、原路径/目标路径、依据摘要、风险与最近一次批量回滚所需最小信息。
- 路径冲突默认停止，不得自动覆盖。
- 最近一次批量回滚必须可用并输出失败清单。

### FR-012 隐私模式与模型路由

- 支持 `Local-Only / Hybrid / Cloud-Assisted` 三种模式。
- `Local-Only` 下禁止外网请求。
- 云端模式只允许发送最小必要证据片段，不得发送整目录全文。
- 当前网络模式和语义模式必须可视化或可审计。

### FR-013 审计与导出

- 扫描、索引、检索、问答、摘要、生成、记忆写入、归档、回滚、外发都必须可审计。
- 必须支持按任务、时间、文件、`trace_id` 查询。
- `SourceRoot`、`ScanRun`、`IndexArtifact`、`FileOperationPlan` 与相关 `TaskEvent` 的链路必须能被串起来回查。
- 审计导出默认不包含全文正文，只包含摘要与定位信息。

### FR-014 配置与密钥管理

- 配置采用 TOML + env 覆盖。
- 密钥通过 keyring 管理，不落入明文配置。
- 缺失配置时要给出清晰提示。
- 日志与异常信息不得泄露完整密钥。

### FR-015 证据检查界面

- 搜索、问答、归档、生成都必须能展示证据面板。
- 引用必须可点击，并定位到页码、段落或字符区间附近。
- 归档依据既要展示内容证据，也要展示辅助信号。

### FR-016 自动化验收与基准工具

- 必须提供 `scripts/generate_fixture_corpus.py` 和 `scripts/run_acceptance.py`。
- 自动化验收必须覆盖解析、索引、搜索、问答、摘要、分类、归档、回滚、记忆、审计、网络隔离。
- 必须能产出 JSON/Markdown 报告、覆盖率报告、静态检查报告和性能结果。

---

## 7. 应用服务契约与边界

### 7.1 核心应用服务

```python
class SourceService:
    add_source(...)
    update_source(...)
    scan_source(...)
    list_scan_runs(...)
    list_sources(...)

class IndexService:
    rebuild_index(...)
    update_index_for_changes(...)
    get_index_status(...)
    get_artifact_status(...)

class SearchService:
    search(...)
    open_document(...)
    locate_evidence(...)

class QAService:
    answer(...)
    summarize(...)
    extract_insights(...)

class ArchiveService:
    classify(...)
    preview_archive_plan(...)
    execute_archive_plan(...)
    rollback_last_batch(...)

class GenerationService:
    generate_draft(...)
    save_output(...)

class TaskEventService:
    record_event(...)
    get_event(...)
    query_events(...)

class MemoryService:
    search_memory(...)
    encode_from_task_event(...)
    consolidate(...)
    resolve_conflict(...)
    disable_memory(...)
    delete_memory(...)
    correct_memory(...)

class AuditService:
    query_logs(...)
    export_logs(...)

class ProviderService:
    list_providers(...)
    test_provider(...)
    route_llm(...)
    route_embedding(...)
```

### 7.2 服务边界

- `SourceService` 是 `SourceRoot` 与 `ScanRun` 的唯一应用层编排入口。
- `IndexService` 负责索引流程与 `IndexArtifact` 状态表达，不得把派生工件状态分散到 UI 或脚本里各自维护。
- `TaskEventService` 是 `TaskEvent` 的唯一写入口。
- `MemoryService` 只能消费已落盘 `TaskEvent`。
- `AuditService` 负责审计，不负责替代 `TaskEventService` 建模任务事件。
- `IndexService`、`SearchService`、`QAService`、`ArchiveService`、`GenerationService` 必须共享同一套解析、chunk、语义表示和引用结构。

### 7.3 UI 禁止直接做的事

- 直接改数据库
- 直接移动、重命名、创建文件
- 直接调用 Provider SDK
- 绕过应用服务层写审计
- 绕过 `TaskEventService` 直接写任务事件

---

## 8. UI 原则与 MVP 页面

### 8.1 UI 原则

- 识别优于回忆
- 风险优先展示
- 引用必须就近可见
- 高风险动作必须先看到差异再允许执行
- 不能要求用户记隐藏命令才能完成核心任务

### 8.2 MVP 页面

1. 初始化向导与设置页
2. 搜索与问答主界面
3. 洞察与摘要页面
4. 归档预览页面
5. 生成编辑页面
6. 记忆管理页面
7. 审计与回滚页面

---

## 9. 安全、隐私与可信性要求

### 9.1 权限分级

| 级别 | 操作 | 规则 |
| --- | --- | --- |
| L1 自动执行 | 搜索、读取、列表、索引、摘要、问答、`memory_encode`、`memory_consolidate`、`memory_promote` | 自动执行并写审计 |
| L2 需确认 | `move / rename / create / save_output / memory_disable / memory_delete / memory_correct` | 先预览或确认再执行 |
| L3 默认禁止 | `delete / purge_memory_all / external_export_bulk` | 默认无入口；启用时需额外审批 |

### 9.2 隐私要求

- `Local-Only` 下外发请求数必须为 0。
- 云端模式仅允许最小必要外发。
- 密钥不写日志，不写明文配置。
- 审计导出默认不包含全文原文。

### 9.3 文件系统安全

- 目标路径冲突默认停止。
- 只允许在受控根目录和输出目录内执行相关写操作。
- 默认不跨盘写入，不隐式覆盖现有文件。

### 9.4 可信性机制

- 引用校验
- 冲突检测
- 语义模式可见
- 内容依据可复核
- 审计可追踪
- 最近一次批量回滚可用

---

## 10. 非功能需求

| ID | 指标 | 目标 |
| --- | --- | --- |
| NFR-001 | 搜索性能 | 1 万文档下搜索 P95 <= 2.5s |
| NFR-002 | 增量索引 | 1000 文档 <= 3 min |
| NFR-003 | 首次启动 | 冷启动 <= 8s（不含首次索引） |
| NFR-004 | 引用跳转 | <= 1.5s |
| NFR-005 | 草稿生成 | 典型月报草稿 <= 20s（本地模型除外） |
| NFR-006 | 事实回答引用覆盖率 | >= 95% |
| NFR-007 | 证据不足拒答正确率 | >= 90% |
| NFR-008 | 冲突检测召回率 | >= 90% |
| NFR-009 | 回滚成功率 | >= 99.9% |
| NFR-010 | 索引任务可恢复 | 失败可重试且不污染已有索引 |
| NFR-011 | 崩溃恢复 | 异常退出后再次启动不损坏主库 |
| NFR-012 | 长会话稳定性 | 长上下文下仍保留证据优先策略 |
| NFR-013 | 写操作审计覆盖率 | 100% |
| NFR-014 | `Local-Only` 外发请求 | 0 |
| NFR-015 | 密钥泄露 | 0 明文落盘日志 |
| NFR-016 | 默认删除风险 | `delete` 默认无入口 |
| NFR-017 | 核心域单元测试覆盖率 | >= 80% |
| NFR-018 | 整体测试覆盖率 | >= 70% |
| NFR-019 | 静态检查 | 全通过 |
| NFR-020 | 文档完备性 | README、架构、配置、验收、隐私、排障文档齐备 |
| NFR-021 | Windows / macOS / Linux 核心用例 | 全通过或有明确待验证矩阵 |
| NFR-022 | 路径处理 | 跨平台差异有测试或回归记录 |
| NFR-023 | 打包产物 | 三平台可生成安装包或发布目录，或有明确构建矩阵 |

---

## 11. 最终固化默认值

- 默认输出目录：`OpenDocs_Output`
- 默认本地模式：`Local-Only`
- 默认检索：混合检索
- 默认语义模式：正常语义模式；统计 fallback 必须显式开启
- 默认 `delete`：禁用
- `M1` 默认复审/硬上限：30 天
- `M2` 默认：关闭
- `M2` 自动晋升阈值：`confidence >= 0.85`
- `M2` 自动晋升最小独立事件数：2
- 低于阈值的偏好写入状态：`promotion_state=candidate`
- 最近一次批量回滚窗口：7 天

---

## 12. 关联权威与桥梁文件

关联文件的完整职责仍以 `0.3` 和 `0.4` 为准；本节只保留快速索引：

- `docs/acceptance/tasks.yaml`：唯一定义阶段排序、阶段门禁、阶段测试命令、出口条件与阶段 `status`
- `docs/acceptance/acceptance_cases.md`：唯一定义最终通过/失败判定、`TC-001 ~ TC-021` 与验收报告契约
- `docs/prompts/codex_operator_prompt.md`：只负责启动代理并约束第一轮输出
- `AGENTS.md`：只负责仓库协作纪律、汇报要求与阻塞格式
- `docs/guides/`：只负责桥梁模板与非开发者说明

桥梁文件不得凌驾于权威文件之上；其他治理文件如需引用裁决链、职责矩阵或遗留实现处理口径，只回指 `0.3`、`0.4`、`2.3`，不再自成第二套主定义。
