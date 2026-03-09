# ADR-0008: 引入 charset-normalizer 处理非 UTF-8 编码

- 状态：已接受
- 日期：2026-03-08
- 关联阶段：S2

## 上下文

主规范 §4.1 锁定技术栈中未列出编码检测库。但实际场景下，中文用户的 .txt 和 .md 文件大量使用 GBK/GB2312/GB18030 编码。若只支持 UTF-8，这些文件要么解析失败，要么产生乱码，直接影响 FR-001（扫描）和 FR-002（索引）的可用性。

## 决策

引入 `charset-normalizer`（纯 Python，无 C 依赖）作为编码检测后备：

1. 优先尝试 UTF-8 strict 解码（零开销快路径）。
2. 失败时用 charset-normalizer 自动检测。
3. 检测置信度不足时，逐一探测常见 CJK 编码（gb18030, gbk, big5, euc-kr, shift_jis）。
4. 最后兜底 utf-8 with errors="replace"。

## 替代方案

- `chardet`：C 扩展，跨平台打包更复杂；charset-normalizer 是 requests 库自带的替代品，更轻量。
- 仅支持 UTF-8：不满足中文用户实际需求。
- 让用户手动指定编码：违反"简单优先"原则。

## 影响

- 新增运行时依赖：`charset-normalizer>=3.3,<4.0`（已加入 pyproject.toml）。
- 仅用于 `src/opendocs/parsers/_encoding.py`，不扩散到其他模块。
- 对打包无额外影响（纯 Python）。

## 回退方案

移除 charset-normalizer 后，`_encoding.py` 的探测仍可通过硬编码 CJK 编码列表工作，只是自动检测准确度下降。
