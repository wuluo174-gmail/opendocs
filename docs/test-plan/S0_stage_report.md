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

## 2. 关键实现说明
- 补齐主规范 7.1 在 `scripts/` 中列出的三个脚本入口，占位实现统一返回 `2`（blocked），避免误判为已实现。
- 新增 `resolve_settings_path`，CLI 在显式 `--config` 时按该配置根目录推导日志目录，不再强制写默认用户目录。
- 增加 smoke 测试覆盖：
  - S0 关键脚本存在性；
  - 显式配置路径时日志落到对应根目录。

## 3. 运行命令
- `python scripts/bootstrap_dev.py`
- `python -m opendocs --help`
- `pytest -q`
- `python -m opendocs`

## 4. 测试结果
- 通过：
  - `python scripts/bootstrap_dev.py`（在 Windows 下会自动委托到 `py -3.11`，并按锁文件安装后校验 `hnswlib`）
  - `python -m opendocs --help`
  - `pytest -q`（45 passed）
  - `python -m opendocs`
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
