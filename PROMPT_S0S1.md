第一性原理阅读代码进行审查，对照S0：项目脚手架与基线和S1：领域模型与存储基线，看看工程施工有没有跑偏或者缺漏，或者其他问题？

如果发现问题，按照以下文件：
docs/specs/OpenDocs_工程实施主规范_v1.0.md
docs/acceptance/tasks.yaml
docs/acceptance/acceptance_cases.md
docs/prompts/codex_operator_prompt.md
AGENTS.md来完善实施；不要扩大范围，不要跳阶段，不要重构整个项目。

请只处理当前 S0和S1 的问题，制定计划并实施，修复你发现的问题。
然后把审查结果和修复结果增量输入到 S0S1audit.md 的文档里作为记录。

【系统级强制指令】：
1. 如果你发现问题并进行了修复，完成后请直接停止并退出。
2. 如果你经过仔细审查，发现【没有任何需要修复的问题】，请在终端执行 `touch .all_clear` 命令创建一个标志文件，然后停止并退出。
3. 本次任务结束后，不要等待用户输入，必须立刻使用工具或者指令退出当前会话。
