# OpenDocs

OpenDocs 是本地优先、证据优先的桌面 AI 文档管理系统。本仓库当前覆盖 S0-S2，并正在收口这些阶段的基线问题。

## 安装

要求：
- 宿主机原生 Python 3.11（锁定基线，不使用 Docker / devcontainer 内的解释器）
- pip

推荐先激活仓库内虚拟环境（确保后续 `python`、`pytest` 命令可直接使用）：

```bash
python3.11 -m venv .venv
source .venv/bin/activate
```

Windows PowerShell：

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
```

安装开发依赖：

```bash
.venv/bin/python scripts/bootstrap_dev.py
```

Windows PowerShell 请将 `.venv/bin/` 替换为 `.venv\\Scripts\\`。

该脚本只会安装 `requirements.lock` 中锁定的第三方依赖，并把当前仓库作为本地 editable 包安装；不会再从远端仓库拉取 `opendocs` 自身代码。
`bootstrap_dev.py` 会校验当前基线的 Python 与安装流程，并额外验证 `hnswlib` 可导入，避免锁定技术栈在 S0 就静默漂移。
项目根目录的 `.python-version` 固定为 `3.11`，供本机解释器管理器、编辑器和终端识别。
本项目不提供 Docker / devcontainer 运行时；如果仓库里已有旧 `.venv` 且它指向不存在的解释器，先移除旧 `.venv`，再用宿主机原生 `Python 3.11` 重建。

如需直接执行主规范中的安装验证命令，请使用 Python 3.11：

```bash
python3.11 -m pip install -e '.[dev]'
```

Windows PowerShell：

```powershell
py -3.11 -m pip install -e ".[dev]"
```

## 运行

查看帮助：

```bash
.venv/bin/python -m opendocs --help
```

查看版本：

```bash
.venv/bin/python -m opendocs --version
```

最小启动：

```bash
.venv/bin/python -m opendocs
```

## 测试

执行阶段基线测试：

```bash
.venv/bin/pytest -q
```

如果当前 shell 没有激活虚拟环境，可用显式路径执行：

```bash
.venv/bin/python -m opendocs --help
.venv/bin/python -m opendocs
.venv/bin/pytest -q
```

## S1 存储基线命令

初始化数据库：

```bash
.venv/bin/python scripts/init_db.py --db-path .tmp/opendocs.db
```

写入样例数据：

```bash
.venv/bin/python scripts/seed_demo_data.py --db-path .tmp/opendocs.db
```

执行存储层单测：

```bash
.venv/bin/pytest tests/unit/storage -q
```

## 目录结构

```text
opendocs/
├─ README.md
├─ pyproject.toml
├─ requirements.lock
├─ .env.example
├─ settings.example.toml
├─ docs/
│  ├─ architecture/
│  ├─ adr/
│  ├─ test-plan/
│  ├─ acceptance/
│  └─ prompts/
├─ src/opendocs/
├─ tests/
└─ scripts/
```

## 常见问题

1. `pytest` 提示找不到 Qt 绑定：重新执行 `.venv/bin/python scripts/bootstrap_dev.py`。
2. 配置文件缺失：默认会使用内置配置；如需自定义，将仓库根目录的 `settings.example.toml` 复制到运行目录的 `config/settings.toml`（macOS 默认为 `~/Library/Application Support/OpenDocs/config/settings.toml`，Linux 为 `~/.local/share/OpenDocs/config/settings.toml`，Windows 为 `%APPDATA%/OpenDocs/config/settings.toml`），或设置 `OPENDOCS_CONFIG` 环境变量指向 TOML 文件。
3. 日志位置：默认在用户数据目录下的 `logs/`，启动时会创建 `app.log`、`audit.jsonl`、`task.jsonl`。
   这三类日志默认按天轮转，保留最近 7 份历史文件。
4. 凭据管理：按阶段计划，keyring 集成在 S10 实现，S0/S1 不提供 Provider 密钥管理接口。
5. 若当前 `python` 不是 3.11：`bootstrap_dev.py` 会在 Windows 上尝试委托给 `py -3.11`；若本机没有可用的宿主机原生 `3.11`，脚本会失败并提示先安装。
6. 若仓库里的 `.venv` 指向不存在的解释器，`bootstrap_dev.py` 会直接失败，避免继续复用失效环境；此时请删除旧 `.venv` 并用宿主机原生 `Python 3.11` 重建。
7. `.doc` 等不支持格式会被明确标记为 `unsupported format`，不会伪装成 `txt` 解析结果。
