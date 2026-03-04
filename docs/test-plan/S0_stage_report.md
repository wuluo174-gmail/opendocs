# 阶段 S0 完成报告

## 1. 新增 / 修改文件
- 新增 `scripts/generate_fixture_corpus.py`
- 新增 `scripts/rebuild_index.py`
- 新增 `scripts/run_acceptance.py`
- 修改 `scripts/bootstrap_dev.py`
- 修改 `src/opendocs/config/settings.py`
- 修改 `src/opendocs/config/__init__.py`
- 修改 `src/opendocs/cli/main.py`
- 修改 `tests/unit/test_bootstrap_dev.py`
- 修改 `tests/unit/test_smoke.py`
- 修改 `.gitignore`
- 新增 `dist/.gitkeep`

## 2. 关键实现说明
- 补齐主规范 7.1 在 `scripts/` 中列出的三个脚本入口，占位实现统一返回 `2`（blocked），避免误判为已实现。
- 新增 `resolve_settings_path`，CLI 在显式 `--config` 时按该配置根目录推导日志目录，不再强制写默认用户目录。
- 增加 smoke 测试覆盖：
  - S0 关键脚本存在性；
  - 显式配置路径时日志落到对应根目录。
- 对齐主规范 7.1 的仓库结构，新增 `dist/.gitkeep` 作为发布目录占位，并通过 `.gitignore` 仅放行该占位文件。

## 3. 运行命令
- `./.venv/bin/python scripts/bootstrap_dev.py`
- `./.venv/bin/python -m opendocs --help`
- `./.venv/bin/pytest -q`
- `./.venv/bin/python -m opendocs`
- `./.venv/bin/ruff check .`

## 4. 测试结果
- 通过：
  - `./.venv/bin/python scripts/bootstrap_dev.py`（按锁文件安装并校验 `hnswlib`）
  - `./.venv/bin/python -m opendocs --help`
  - `./.venv/bin/pytest -q`
  - `./.venv/bin/python -m opendocs`
  - `./.venv/bin/ruff check .`
- 失败：
  - 无
- 覆盖范围：
  - S0 脚手架入口、配置加载、日志初始化、smoke 测试

## 5. 已知问题 / 风险
- 运行环境若缺少 Python 3.11（且 Windows 下不可用 `py -3.11`），`bootstrap_dev.py` 会按预期失败并提示安装 3.11。

## 6. 出口条件判定
- [x] 本地可安装依赖
- [x] `pytest` 空跑成功
- [x] `python -m opendocs` 可启动
- [x] README 写清运行方式

## 7. 下一阶段计划
- 进入 S1，仅处理 seed 脚本副作用与对应测试，避免写入仓库工作区。

## 8. 2026-03-04 修订记录
- `bootstrap_dev.py` 改为锁文件安装（`requirements.lock`）并强制校验 `hnswlib`，不再以“降级成功”作为通过条件。
- Windows 下若入口解释器非 3.11，脚本会自动委托 `py -3.11`；若不可用则显式失败。
- `bootstrap_dev.py` 的 editable 安装目标改为仓库绝对路径（不再依赖当前工作目录必须是仓库根目录）。
- 修正 CLI 的配置根目录推导：显式 `--config` 为非 `config/settings.toml` 布局时，日志落在该配置文件同级根目录的 `logs/`。
- 修正 Python 基线口径漂移：`pyproject.toml` 收敛为 `>=3.11,<3.12`，`requirements.lock` 头注释去除“3.12 compatible”描述，并补充对应单测防回归。
- 补充 README 的虚拟环境激活与显式路径命令，降低“系统无 `python` 别名”导致的复验失败风险。
- 修正 `test_cli_default_start_smoke`：使用临时 `OPENDOCS_CONFIG`，避免 macOS/Linux 回落到真实用户目录。
- `requirements.lock` 从“仅直接依赖”改为“直接 + 传递依赖全量锁定”，提升长期可重复安装稳定性。
- `bootstrap_dev.py` 的 editable 安装增加 `--no-build-isolation`，确保离线/受限网络下不因构建隔离拉取依赖而失败。
- 修复 CI `ruff` 门禁失败：仓储层 5 个 `delete` 方法中的长字符串改为多行表达，消除 `E501`。
- S0/S1 的 `tasks.yaml` 阶段命令切换为 `.venv` 解释器与 `pytest` 路径，避免环境缺少 `python` 别名导致复验失败。
- 修正 S0 验收映射口径：`acceptance_refs` 从 `TC-019` 调整为 `[]`，避免把 S11 的“一键验收”能力前置到 S0 阶段门禁。
- 对齐占位语料脚本 CLI 契约：`scripts/generate_fixture_corpus.py` 新增 `--profile` 与 `--output` 参数（保留 `--output-dir` 兼容别名），与 `acceptance_cases.md` 用法一致。
- 补充 S0 smoke 测试：断言 `generate_fixture_corpus.py --profile acceptance --output .tmp/corpus` 返回 `2`（blocked）且输出包含请求参数，防止后续参数回归漂移。
- 修复主规范 7.1 目录轻微偏差：新增 `dist/.gitkeep`，并在 `.gitignore` 中仅豁免该占位文件，保证仓库可追踪 `dist/` 目录骨架且不引入构建产物。
- 修复 CI 格式门禁漂移：执行 `ruff format` 对齐 `src/opendocs/domain/models.py` 与 `tests/unit/storage/test_migrations.py`，`ruff format --check .` 恢复通过。
- 修复 README 在 zsh 的安装命令复现问题：将 `pip install -e .[dev]` 调整为可直接执行的 `python3.11 -m pip install -e '.[dev]'`，并补充 Windows PowerShell 对应写法。
