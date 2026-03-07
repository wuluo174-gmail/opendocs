# OpenDocs

OpenDocs 是本地优先、证据优先的桌面 AI 文档管理系统。本仓库当前完成 S1（领域模型与存储基线）。

## 安装

要求：
- Python 3.11（锁定基线）
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
python scripts/bootstrap_dev.py
```

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
python -m opendocs --help
```

查看版本：

```bash
python -m opendocs --version
```

最小启动：

```bash
python -m opendocs
```

## 测试

执行阶段基线测试：

```bash
pytest -q
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
python scripts/init_db.py --db-path .tmp/opendocs.db
```

写入样例数据：

```bash
python scripts/seed_demo_data.py --db-path .tmp/opendocs.db
```

执行存储层单测：

```bash
pytest tests/unit/storage -q
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

1. `pytest` 提示找不到 Qt 绑定：重新执行 `python scripts/bootstrap_dev.py`。
2. 配置文件缺失：默认会使用内置配置；如需自定义，将仓库根目录的 `settings.example.toml` 复制到运行目录的 `config/settings.toml`（macOS 默认为 `~/Library/Application Support/OpenDocs/config/settings.toml`，Linux 为 `~/.local/share/OpenDocs/config/settings.toml`，Windows 为 `%APPDATA%/OpenDocs/config/settings.toml`），或设置 `OPENDOCS_CONFIG` 环境变量指向 TOML 文件。
3. 日志位置：默认在用户数据目录下的 `logs/app.log`。
4. 凭据管理：按阶段计划，keyring 集成在 S10 实现，S0/S1 不提供 Provider 密钥管理接口。
5. 若当前 `python` 不是 3.11：`bootstrap_dev.py` 会在 Windows 上尝试委托给 `py -3.11`；若本机没有可用 3.11，则脚本会失败并提示先安装 Python 3.11。
