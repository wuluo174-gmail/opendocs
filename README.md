# OpenDocs

OpenDocs 是本地优先、证据优先的桌面 AI 文档管理系统。本仓库当前完成 S0（项目脚手架与基线）。

## 安装

要求：
- Python 3.11 或 3.12（CI 固定 3.11）
- pip

安装开发依赖：

```bash
python scripts/bootstrap_dev.py
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
2. 配置文件缺失：默认会使用内置配置；如需自定义，可设置 `OPENDOCS_CONFIG` 指向 TOML 文件。
3. 日志位置：默认在用户数据目录下的 `logs/app.log`。
