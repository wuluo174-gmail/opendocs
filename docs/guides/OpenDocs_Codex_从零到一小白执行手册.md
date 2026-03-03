# OpenDocs 用 ChatGPT-Codex 从零到一小白执行手册 v1.0

版本日期：2026-03-02  
适用对象：不会写代码、但要用 Codex 把 OpenDocs 项目做出来的人  
默认工程：OpenDocs 本地优先 AI 文档管理系统

---

## 0. 先说结论：你现在应该走哪条路线

### 0.1 我给你的默认路线

**默认路线：VS Code + Codex IDE 扩展 + 本地运行（Local） + Git 检查点 + 分阶段推进。**

原因很简单：

1. 你已经在用 VS Code 里的 Codex 扩展，继续沿着这个路径走，学习成本最低。
2. 这个项目要处理的是**你电脑里的本地文档**，所以主战场应该是 **Local 模式**，不是 Cloud。OpenAI 官方说明，本地线程会在你的机器上运行，可以直接读写工作区文件；Cloud 线程则运行在隔离环境里，通常更适合并行委托、远程环境或 GitHub 仓库任务。  
3. Codex 官方明确支持在 IDE 中使用 `Chat`、`Agent` 和 `Agent (Full Access)` 三种模式。对你这种非开发者，最稳的操作方式是：**先用 Chat 计划，再用 Agent 实施，除非万不得已，不用 Full Access。**

[官方依据：Quickstart / IDE features / Prompting]

### 0.2 如果你是 Windows 用户，必须先做这件事

如果你是 **Windows** 用户，我建议你把 **VS Code + WSL2 工作区** 作为唯一正路。OpenAI 官方写得很清楚：  
- VS Code 扩展在 Windows 上是**实验性支持**；  
- 想要更好的 Windows 体验，建议在 **WSL 工作区** 中使用；  
- 并且 Codex 的 Agent 模式在 Windows 当前要求 WSL。  

**你如果在 Windows 上直接拿 `C:\...` 本地目录硬干，大概率会在权限、性能、Agent 能力、路径、终端环境上反复卡死。**

[官方依据：IDE extension / Windows guide]

### 0.3 如果你是 macOS 用户

如果你是 **macOS Apple Silicon** 用户，而且你还没正式开工，那么官方 Quickstart 把 **Codex App** 标成了“Recommended”。不过这个项目本身是一个完整仓库工程，涉及很多规范文件、测试、目录和差异审查。  
所以即便你是 macOS，我仍然建议你把 **VS Code 扩展** 当作主工作台；Codex App 可以以后再作为补充工具用。

[官方依据：Quickstart / Codex app]

### 0.4 你在整个项目里只需要做 5 类动作

你不是程序员，所以你不要试图“亲自写代码”。你只需要学会下面 5 类动作：

1. **打开正确的工程目录**
2. **把正确的规范文件给 Codex 看**
3. **告诉 Codex 现在只做哪个阶段**
4. **检查它是否真的运行了测试、是否越界改动**
5. **做 Git 检查点，必要时回滚**

你全程的角色不是“开发者”，而是：

- 项目负责人
- 规则守门员
- 审批人
- 验收人
- 回滚决策人

---

## 1. 你要先理解的几个最重要概念

### 1.1 Chat、Agent、Agent (Full Access) 分别什么时候用

根据官方文档：[官方依据：IDE features]

- `Chat`：适合聊天、计划、讨论、先想清楚再动手。
- `Agent`：默认模式。可以在工作目录里读文件、改文件、跑命令；如果要访问工作目录外或访问网络，仍会请求批准。
- `Agent (Full Access)`：可以不经批准地更广泛读写、运行命令和访问网络，官方明确提醒要谨慎使用。

**给你的规则：**

- **计划时**：用 `Chat`
- **写代码、跑测试时**：用 `Agent`
- **默认禁用 `Agent (Full Access)`**
- **Cloud**：先不用，除非你已经会本地流程，而且需要并行委托

### 1.2 Local 和 Cloud 的区别

官方文档说明：

- **Local 线程**：在你自己的机器上运行，能直接读写你的工作区文件。
- **Cloud 线程**：在隔离环境中运行，通常需要 GitHub 仓库或已配置的云环境。

OpenDocs 的核心对象是**你本机里的文本文档和本地代码仓库**，因此：

- **主流程一律用 Local**
- **Cloud 不是主路线**
- 只有当你未来做纯代码型长任务、并且不依赖本地文档时，才考虑 Cloud

### 1.3 为什么我建议“一阶段一个线程”

官方文档提到，Codex 会使用上下文窗口，并在对话变长时进行压缩（compaction）。  
这意味着对话太长之后，虽然它能继续工作，但上下文会被总结和压缩，细节漂移的概率会上升。

所以我建议：

- **一个阶段一个主线程**
- 遇到严重跑偏或记忆污染时，新开线程，不要死扛
- 修改 `AGENTS.md` 或 `.codex/config.toml` 后，也最好新开线程

---

## 2. 一次性环境准备：你从零开始应该先做什么

> 这一节是“第一次装环境”。做完一次，后面就进入项目节奏。

### 2.1 所有人都要装的东西

你至少需要这些：

- VS Code
- OpenAI Codex IDE 扩展
- Git
- Python 3.11
- 你的 OpenAI / ChatGPT 登录方式

官方 Quickstart 说明：Codex 扩展安装后会出现在侧边栏里，你可以用 **ChatGPT 账号或 API key** 登录开始使用。  
对你这种非开发者，我更建议你直接用**自己的 ChatGPT 账号**登录，这样少一层 API key 费用和配置心智负担。

### 2.2 如果你是 Windows：按这个顺序来

#### 第一步：安装 WSL

1. 用管理员身份打开 PowerShell
2. 执行：

```powershell
wsl --install
```

官方 Windows 指南就是这样写的。

#### 第二步：装 VS Code 的 WSL 扩展

你需要让 VS Code 能打开 WSL 工作区。

#### 第三步：把项目放在 WSL 的 Linux 家目录里，不要放在 `C:` 盘映射路径

官方 Windows 指南特别提醒：  
把仓库放在 Linux 家目录，比如 `~/code/my-app`，而不要放在 `/mnt/c/...`。  
后者通常更慢，也更容易遇到权限、符号链接和路径问题。

建议这样做：

```bash
mkdir -p ~/code
cd ~/code
mkdir OpenDocs
cd OpenDocs
code .
```

#### 第四步：确认你确实在 WSL 里打开了工程

你应该看到：

- VS Code 左下或状态栏里显示 `WSL: Ubuntu` 之类的信息
- 集成终端里显示 Linux 路径，比如 `/home/...`
- 运行：

```bash
echo $WSL_DISTRO_NAME
```

会输出你的发行版名字

#### 第五步：打开 Codex 的 WSL 相关设置

在 VS Code 设置里搜索：

```text
chatgpt.runCodexInWindowsSubsystemForLinux
```

官方把这个设置标注为：**Windows 推荐在 WSL 中运行 Codex**，以获得更好的安全沙箱和性能。

#### 第六步：如果装好了扩展却没反应

官方 Windows 文档给出的常见修复包括：

- 安装 Visual Studio Build Tools（C++ workload）
- 安装 Microsoft Visual C++ Redistributable（x64）
- 然后完整重启 VS Code

### 2.3 如果你是 macOS / Linux

你可以直接：

1. 打开 VS Code
2. 安装 Codex 扩展
3. 打开工程目录
4. 登录
5. 开始工作

如果你是 **macOS Apple Silicon**，官方 Quickstart 里把 **Codex App** 作为推荐路线之一；但本手册仍以 VS Code 扩展为主，因为它更适合按文件、按阶段、按差异来管这个项目。

### 2.4 第一次打开 Codex 后，你先检查这 4 件事

1. 扩展面板能否正常打开
2. 你能否登录成功
3. 你能否在当前工程里看到 Codex 聊天框
4. 你能否切换 `Chat` / `Agent` / `Local`

如果这 4 件事做不到，**先不要开工写项目**，先把环境问题解决。

---

## 3. 把工程摆正：你要把哪些文件放到哪里

你现在已经有这些关键文件：

- `OpenDocs_工程实施主规范_v1.0.md`
- `tasks.yaml`
- `acceptance_cases.md`
- `codex_operator_prompt.md`

建议你把它们摆成下面这个结构：

```text
OpenDocs/
├─ AGENTS.md
├─ .codex/
│  └─ config.toml
├─ docs/
│  ├─ specs/
│  │  └─ OpenDocs_工程实施主规范_v1.0.md
│  ├─ acceptance/
│  │  ├─ tasks.yaml
│  │  └─ acceptance_cases.md
│  ├─ prompts/
│  │  └─ codex_operator_prompt.md
│  └─ guides/
│     ├─ OpenDocs_Codex_从零到一小白执行手册.md
│     └─ OpenDocs_Codex_阶段提示词清单.md
└─ （后续由 Codex 生成的代码目录）
```

### 3.1 为什么一定要有 `AGENTS.md`

官方说明，Codex 会在开始工作前自动读取 `AGENTS.md`，并且会按“全局 -> 项目根 -> 当前目录”的顺序叠加这些指令。  
这正适合你这种场景：你不想每一轮都重新解释“不要跳阶段”“不要换技术栈”“一定要跑测试”。

### 3.2 为什么一定要有 `.codex/config.toml`

官方说明，IDE 扩展和 CLI 共享 `config.toml` 配置层；项目里的 `.codex/config.toml` 可以覆盖用户级默认配置，而且项目配置只有在**你信任工作区**时才会生效。  
这正好可以把本项目的默认运行方式固定下来，比如：

- 允许在工作区内写代码
- 不允许网络
- 使用 `on-request` 审批
- 默认模型和推理强度固定

---

## 4. 先做第一个 Git 检查点：这是你的“后悔药”

官方 Quickstart 明确建议：  
Codex 可能修改代码，因此在每个任务前后都做 Git 检查点，便于回滚。

### 4.1 如果你不会 Git，你只要会这 3 个动作

#### 动作 1：初始化仓库

在 VS Code 里：

- 打开左侧 **Source Control（源代码管理）**
- 点击 **Initialize Repository**

#### 动作 2：第一次提交

把当前文件都纳入版本管理，提交信息写：

```text
checkpoint: project bootstrap before Codex work
```

#### 动作 3：每完成一个阶段，再做一次提交

例如：

```text
checkpoint: S0 complete
checkpoint: S1 complete
checkpoint: S2 complete
```

### 4.2 你的简单规则

- **开始一个阶段前**：先提交一次
- **通过一个阶段后**：再提交一次
- **Codex 跑偏**：回到上一个阶段提交点

如果你完全不想碰 Git 命令行，用 VS Code 图形界面也可以。  
如果你更喜欢可视化，再额外装个 GitHub Desktop 也行，但不是必须。

---

## 5. 你要先放进仓库的两个关键文件

> 我已经给你准备了模板：`AGENTS.md` 和 `.codex/config.toml`。  
> 你只需要把它们放进仓库根目录对应位置即可。

### 5.1 `AGENTS.md` 负责什么

它负责把**工程纪律**固定住：

- 只做一个阶段
- 不跳阶段
- 不私自换技术栈
- 必须跑测试
- 必须输出阶段报告
- 遇到阻塞先最小修复，不要推倒重来
- 用中文解释给非开发者看

### 5.2 `.codex/config.toml` 负责什么

它负责把**默认运行约束**固定住：

- `approval_policy = "on-request"`
- `sandbox_mode = "workspace-write"`
- `network_access = false`
- `web_search = "disabled"`
- 合理的默认模型与推理强度

> 说明：官方默认本地任务会启用缓存型 web search，但这个项目的主规范已经足够明确，而且本项目强调本地优先、证据优先，所以我的建议是：**项目级配置里直接关掉 web search**，避免 Codex被网络信息带偏。

---

## 6. 第一次真正启动项目前，你要做的固定动作

每次真正开始一个阶段前，都照这个顺序做：

### 6.1 打开正确的工作区

- Windows：确认你是在 WSL 工作区里
- macOS / Linux：确认打开的是仓库根目录
- 不要只打开某个子文件夹
- 不要让 Codex 在一个“空目录”里工作

### 6.2 打开这些文件标签页

最少打开下面 5 个文件：

- `docs/specs/OpenDocs_工程实施主规范_v1.0.md`
- `docs/acceptance/tasks.yaml`
- `docs/acceptance/acceptance_cases.md`
- `docs/prompts/codex_operator_prompt.md`
- `AGENTS.md`

官方文档说明，IDE 扩展会自动把**当前打开的文件**和**选中的文本范围**作为上下文；另外你也可以在提示词里用 `@文件名` 显式引用文件。  
所以最稳的做法是：**既打开文件，又在提示词中显式提文件名。**

### 6.3 先切换到 Local，再看状态

在 Codex 输入框里依次做：

```text
/local
/status
```

`/local` 会把线程切回本地模式，`/status` 会显示当前线程 ID、上下文使用情况等信息。  
这是每次开工前最简单、最不容易出错的“自检动作”。

### 6.4 先用 Chat 模式，不要直接 Agent

你第一次进入某个阶段时，**先用 Chat 模式**发“阶段启动提示词”，让 Codex：

1. 复述当前阶段目标
2. 列出准备修改的文件
3. 说明打算怎么测

只有当这个计划看起来正常时，再切到 `Agent` 去执行。

---

## 7. 你的日常固定工作流：每个阶段都这么干

这一节最重要。  
你以后几乎就是反复执行这套动作。

### 第 1 步：新开一个阶段线程

命名建议：

- `S0-main`
- `S1-main`
- `S2-main`

为什么这样做：  
一是为了防止上下文越滚越长；  
二是为了让你自己知道“现在做到哪一阶段了”。

### 第 2 步：发阶段启动提示词

我另外给你准备了一个独立文件：`OpenDocs_Codex_阶段提示词清单.md`。  
你只要找到当前阶段，把那一段复制给 Codex 就行。

### 第 3 步：看计划，不看代码细节

你是非开发者，所以你不要逐行看代码。  
你只看 4 件事：

1. **它做的是不是当前阶段**
2. **它改的文件多不多、是否相关**
3. **它有没有明确测试命令**
4. **它有没有说“先不做下一阶段”**

### 第 4 步：切到 Agent 执行

如果计划没问题，切到 `Agent`，发执行提示词。

### 第 5 步：只审这 4 类安全点

当 Codex 申请动作、输出结果、给你看变更时，你只检查：

- 有没有超出仓库根目录
- 有没有请求联网
- 有没有想装一堆新框架
- 有没有改了一堆和当前阶段无关的文件

### 第 6 步：看测试结果，不要只看它嘴上说通过

这是最容易犯的大错之一。  
**Codex 说“应该可以通过”不算通过。**  
你只认：

- 它实际运行了命令
- 终端输出里确实通过了
- 阶段报告里写明了结果

### 第 7 步：用 `/review` 或 Source Control 看差异

官方提供了 `/review`，你也可以直接看 VS Code 左侧 Source Control。  
你不需要看懂所有代码，只要看：

- 改动文件数量是否合理
- 有没有大面积删除
- 有没有改到不相关目录
- 有没有把规范文件和说明文档一起更新

### 第 8 步：阶段通过后立刻做 Git 检查点

提交信息按阶段来写：

```text
checkpoint: S3 complete
```

### 第 9 步：再开始下一阶段

**不要在同一轮提示里让它自动从 S3 一口气做到 S7。**  
这是非开发者最容易被 AI 带偏的地方之一。

---

## 8. 12 个阶段，你什么时候该做什么

下面是你整个项目的路线图。  
你不需要记技术细节，只需要知道每个阶段的**目的、你的工作重点、阶段完成后你应该看到什么**。

### S0 - 项目脚手架与基线

**目的：** 让仓库能跑起来，有基础目录、配置、最小入口和最小测试。  
**你要盯：**

- 有没有 `README.md`
- 有没有 `pyproject.toml`
- 能不能运行 `python -m opendocs --help`
- `pytest -q` 能不能跑

**如果 S0 都没过：** 后面一律不许做。

### S1 - 领域模型与存储基线

**目的：** 建好数据库、表结构、仓储层。  
**你要盯：**

- 能不能初始化数据库
- 能不能写入和读取核心实体
- CRUD 和迁移测试是否存在并能通过

### S2 - 解析器与切片器

**目的：** 能解析 `.txt`、`.md`、`.docx`、文字层 `.pdf`。  
**你要盯：**

- 四类文档都能解析
- 单个坏文件不会拖垮整个批量任务
- chunk 是否保留定位信息

### S3 - 扫描、全量索引与增量更新

**目的：** 能扫描目录、做初次索引，并监听后续文档增删改。  
**你要盯：**

- 初次全量索引能完成
- 新增文档后能补索引
- 删除文档后索引能同步
- 重建索引不乱套

### S4 - 混合检索与证据定位

**目的：** 搜索能返回真正可引用的文档结果。  
**你要盯：**

- 搜索结果里是否真的有引用
- 能不能打开文件位置
- 能不能定位到片段

### S5 - 问答、摘要与洞察

**目的：** 能基于证据回答、摘要和发现冲突。  
**你要盯：**

- 事实问答是否默认附引用
- 证据不足是否拒答
- 冲突证据是否展示冲突，而不是硬给唯一答案

### S6 - 分类、归档计划与回滚

**目的：** 先给归档计划，再执行；执行后还能回滚。  
**你要盯：**

- 拒绝计划后是否零写操作
- 批量操作后能不能回滚
- 路径冲突是否有保护

### S7 - 生成与模板系统

**目的：** 生成周报、月报、纪要等草稿，并保留引用。  
**你要盯：**

- 模板是否可用
- 保存前是否可编辑
- 输出里是否保留引用

### S8 - 记忆体系与冲突治理

**目的：** 区分临时记忆、任务记忆、偏好记忆，防止记忆污染事实。  
**你要盯：**

- M2 默认是否关闭
- 记忆删除后是否不能再被召回
- 冲突记忆是否能被定位、修正、清理

### S9 - 桌面 UI 完整化

**目的：** 真正把功能放进桌面界面，而不是只有脚本。  
**你要盯：**

- 搜索、证据查看、归档预览、生成编辑、记忆管理是否都能在 UI 操作
- 高风险操作是否都有预览和确认
- 是否真的能端到端演示

### S10 - 隐私模式、提供商适配与安全收口

**目的：** 完成本地模式、混合模式、云辅助模式；密钥管理；审计与脱敏。  
**你要盯：**

- Local-Only 是否做到 0 外发
- 云端模式是否能看到外发摘要
- 密钥是否没有写进日志或明文配置

### S11 - 性能调优、打包与验收

**目的：** 跑完验收脚本、打包、做用户文档并形成交付件。  
**你要盯：**

- `run_acceptance.py` 是否全绿
- 打包目录是否能产出
- 用户文档是否齐全
- 最终交付报告是否存在

---

## 9. 你应该什么时候批准，什么时候立刻叫停

### 9.1 可以批准的动作

一般来说，这些动作风险比较低：

- 在仓库里新建/修改代码文件
- 在仓库里新建测试
- 运行 `pytest`
- 运行本阶段定义的脚本
- 更新 `README`、`docs/`
- 在仓库内创建正常的目录结构

### 9.2 暂停并确认的动作

这些动作不要直接点同意：

- 想联网安装依赖
- 想用 `Agent (Full Access)`
- 想修改工作区外的文件
- 想改 `.git`、`.codex`、系统配置
- 想引入新的大型框架
- 想大量删除、重命名、移动文件
- 想“顺便”把几个阶段一起做完

### 9.3 直接叫停的动作

一旦出现下面这些情况，立即停：

- 它开始实现 **delete** 默认删除逻辑
- 它在没有预览/确认的情况下写归档逻辑
- 它让记忆覆盖文档证据
- 它给事实性回答但没有引用
- 它跳过测试直接宣布完成
- 它说“为了快一点，我把技术栈换成别的更熟悉的框架”

---

## 10. 遇到问题时，你不要慌，用下面这些固定招式

### 10.1 Codex 开始跑偏：新开线程，不要硬聊下去

症状：

- 说着 S3，突然开始做 UI
- 开始引入主规范里没有的大框架
- 开始谈未来阶段，而不是当前阶段

处理办法：

1. 停止当前线程
2. 新开一个线程
3. 再次打开规范文件
4. 重新复制当前阶段提示词
5. 明确写：**只允许做当前阶段，不得进入下一阶段**

### 10.2 Codex 没看见关键文件

症状：

- 它好像不知道主规范存在
- 它没有按 `tasks.yaml` 的阶段办事
- 它输出的结构和你要求的不一致

处理办法：

- 确保相关文件真的在编辑器里打开
- 在提示词里显式写 `@docs/specs/...`
- 必要时重新发一次：

```text
请先阅读并总结以下文件，再开始：
@docs/specs/OpenDocs_工程实施主规范_v1.0.md
@docs/acceptance/tasks.yaml
@docs/acceptance/acceptance_cases.md
@docs/prompts/codex_operator_prompt.md
@AGENTS.md
```

### 10.3 测试一直不过

不要让它“继续大改”。  
你应该直接发：

```text
不要扩大范围，不要重构整个项目。
请只分析当前失败测试的最小原因，给出最小修复补丁，然后只复跑失败测试及本阶段要求的测试命令。
```

### 10.4 Windows 下 Agent 不工作

先排查这几个点：

1. 你是不是在 **WSL 工作区** 里
2. 仓库是不是放在 `~/code/...` 而不是 `/mnt/c/...`
3. VS Code 设置里是否开启了 `chatgpt.runCodexInWindowsSubsystemForLinux`
4. VS Code 是否完整重启过
5. 是否缺少 Build Tools / VC++ 运行库

### 10.5 改了 `AGENTS.md` 或 `.codex/config.toml` 但没生效

因为 Codex 的规则读取是**有会话边界**的。  
最稳妥的做法是：

- 结束当前聊天
- 新开线程
- 必要时重载 VS Code 窗口
- 再重新开始当前阶段

---

## 11. 你每天实际应该怎么干：一个最省脑子的节奏

下面是我建议你的**标准工作节奏**。  
你以后基本照着这个顺序重复即可。

### 每次开工前

1. 打开正确仓库
2. 检查是不是当前阶段
3. 打开 5 个规范文件
4. `/local`
5. `/status`
6. 切 `Chat`
7. 复制当前阶段提示词

### 计划通过后

1. 切 `Agent`
2. 发执行提示词
3. 等它改代码和跑测试
4. 检查差异和测试结果
5. 要它输出阶段完成报告

### 阶段通过后

1. 做 Git 提交：`checkpoint: Sx complete`
2. 关闭该线程
3. 记录当前做到哪一阶段
4. 下次再开新线程做下一阶段

---

## 12. 最后验收时，你只认这几件事

当它说“项目完成”时，你不要立刻相信。  
你只认以下四类证据：

### 12.1 自动化验收证据

至少要有：

- `scripts/run_acceptance.py`
- 能执行完整验收
- `TC-001` 到 `TC-020` 的通过记录

### 12.2 功能演示证据

你至少要亲自确认：

- 能加文档源并扫描
- 能搜到文档并看到引用
- 能做问答且附引用
- 证据不足会拒答
- 能给出归档预览
- 拒绝后不执行
- 执行后可回滚
- 能生成月报/周报草稿
- Local-Only 下无外发

### 12.3 交付物证据

至少应该存在：

- 可运行的应用目录或打包产物
- `README.md`
- 用户手册
- 隐私/安全说明
- 故障排查说明
- 最终交付报告

### 12.4 代码仓库证据

你应该能看到：

- 每一阶段至少一个检查点提交
- 没有大量无意义临时文件
- 规范文件仍保留
- 没有把密钥、日志或敏感信息提交进仓库

---

## 13. 你最容易犯的 12 个低级错误

1. **在 Windows 里不用 WSL，直接在 C 盘硬干**
2. **一上来就让 Codex 从 S0 一口气做到 S11**
3. **不做 Git 检查点**
4. **只听 Codex 说“应该通过”，不看测试输出**
5. **让它开 `Agent (Full Access)` 图省事**
6. **发现跑偏了还在原线程里硬聊 40 轮**
7. **规范文件没打开、没引用，就让它盲做**
8. **S0 没过就往后做**
9. **明明是当前阶段失败，却允许它大重构**
10. **看到它引入新框架也没制止**
11. **不看差异，直接接受修改**
12. **它说“项目完成”，你就真的相信了**

---

## 14. 我给你的最终执行建议

如果你只记住 6 句话，就记住这 6 句：

1. **Windows 一律走 WSL 工作区。**
2. **一个阶段一个线程。**
3. **先 Chat 计划，再 Agent 实施。**
4. **每阶段前后都做 Git 检查点。**
5. **只认真实测试输出，不认口头通过。**
6. **不跳阶段，不开 Full Access，不让它越界。**

---

## 15. 你现在就该做的第一批动作

按顺序做，不要跳：

1. 选好你的工程根目录  
2. 把我给你的 starter pack 放进去  
3. 如果你是 Windows，先把仓库放进 WSL 的 `~/code/OpenDocs`  
4. 在 VS Code 打开仓库根目录  
5. 安装并登录 Codex 扩展  
6. 确认工作区已 Trust  
7. 打开 5 个关键规范文件  
8. 初始化 Git 仓库并做第一次提交  
9. 在 Codex 中执行 `/local` 和 `/status`  
10. 新开线程 `S0-main`  
11. 从《OpenDocs_Codex_阶段提示词清单.md》里复制 **S0 提示词** 发给 Codex  
12. **只推进 S0，不要做 S1**

---

## 16. 术语小词典（你只需要知道这些）

- **仓库 / Repo**：项目总文件夹
- **工作区 / Workspace**：VS Code 当前打开的项目根目录
- **Diff / 差异**：这次改了哪些文件、删了哪些内容、加了哪些内容
- **Commit / 提交**：给当前一个可回退的版本打钉子
- **Stage / 阶段**：项目施工顺序上的一个关卡
- **Gate / 门禁**：进入下一阶段前必须满足的条件
- **Test / 测试**：验证当前改动是否真的正常
- **Acceptance / 验收**：最终是否达标的检查

---

## 17. 官方依据（建议收藏）

> 下面这些都是我写这份手册时参考的官方资料。  
> 你以后如果怀疑某个流程是不是过时了，优先看这些官方页。

1. OpenAI, **Codex Quickstart**  
2. OpenAI, **Codex IDE extension**  
3. OpenAI, **Codex IDE extension features**  
4. OpenAI, **Codex IDE extension settings**  
5. OpenAI, **Windows - Best practices for running Codex**  
6. OpenAI, **Codex app**  
7. OpenAI, **Prompting**  
8. OpenAI, **Custom instructions with AGENTS.md**  
9. OpenAI, **Codex IDE extension slash commands**  
10. OpenAI, **Config basics**  
11. OpenAI, **Security**  
12. OpenAI, **Workflows**  
13. OpenAI, **Sample Configuration**

---

## 18. 这份手册怎么配合其他文件一起用

你现在手上应该至少有下面这些文件：

- `docs/specs/OpenDocs_工程实施主规范_v1.0.md`
- `docs/acceptance/tasks.yaml`
- `docs/acceptance/acceptance_cases.md`
- `docs/prompts/codex_operator_prompt.md`
- `AGENTS.md`
- `.codex/config.toml`
- `docs/guides/OpenDocs_Codex_从零到一小白执行手册.md`
- `docs/guides/OpenDocs_Codex_阶段提示词清单.md`

**它们的分工：**

- 主规范：定义“要做成什么”
- tasks：定义“按什么顺序施工”
- acceptance：定义“怎样算通过”
- operator prompt：定义“Codex 的施工纪律”
- AGENTS：定义“仓库层面的持久规则”
- config：定义“Codex 的默认运行方式”
- 小白手册：定义“你什么时候该做什么”
- 阶段提示词清单：定义“你每一轮该复制什么给 Codex”

---

**手册结束。**


## 参考资料

- OpenAI, *Codex Quickstart*. https://developers.openai.com/codex/quickstart/
- OpenAI, *Codex IDE extension*. https://developers.openai.com/codex/ide/
- OpenAI, *Codex IDE extension features*. https://developers.openai.com/codex/ide/features/
- OpenAI, *Codex IDE extension settings*. https://developers.openai.com/codex/ide/settings/
- OpenAI, *Windows - Best practices for running Codex*. https://developers.openai.com/codex/windows/
- OpenAI, *Codex app*. https://developers.openai.com/codex/app/
- OpenAI, *Prompting*. https://developers.openai.com/codex/prompting/
- OpenAI, *Custom instructions with AGENTS.md*. https://developers.openai.com/codex/guides/agents-md/
- OpenAI, *Codex IDE extension slash commands*. https://developers.openai.com/codex/ide/slash-commands/
- OpenAI, *Config basics*. https://developers.openai.com/codex/config-basic/
- OpenAI, *Security*. https://developers.openai.com/codex/security/
- OpenAI, *Workflows*. https://developers.openai.com/codex/workflows/
- OpenAI, *Sample Configuration*. https://developers.openai.com/codex/config-sample/
