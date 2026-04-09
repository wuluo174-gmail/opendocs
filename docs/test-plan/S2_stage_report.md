# S2 阶段完成报告：解析器与切片器

## 1. 新增/修改文件列表

本节只记录当前仓库中仍然存在、且仍由 S2 主链路消费的 owner / 交付物快照。历史审计记录、已收口分支和迁移前实现只能写入后续修复记录，不能继续冒充当前交付物。

### 当前主链路源码
- `src/opendocs/parsers/base.py` — `ParsedDocument`、`ParseError`、`BaseParser` 模板方法、`ParserRegistry`
- `src/opendocs/parsers/txt_parser.py` — TXT 原始提取
- `src/opendocs/parsers/md_parser.py` — Markdown 标题层级与 frontmatter 提取
- `src/opendocs/parsers/docx_parser.py` — DOCX 段落、表格、标题路径提取
- `src/opendocs/parsers/pdf_parser.py` — 文字层 PDF 提取、页码与 TOC 标题路径
- `src/opendocs/parsers/normalization.py` — 统一文本归一化边界
- `src/opendocs/indexing/chunker.py` — 结构 + 语义联合切片

### 当前主链路测试
- `tests/unit/parsers/` — parser 契约、失败隔离、归一化、offset、一致性回归
- `tests/unit/indexing/test_chunker.py` — chunk 定位、边界、重叠比例、失败文档回归
- `tests/integration/indexing/test_full_index.py` — `TC-001` / `TC-002` 映射验收

### 当前阶段文档
- `docs/test-plan/S2audit.md` — S2 审查与修复历史
- `docs/test-plan/S2_stage_report.md` — 本文件

## 2. 关键实现说明

### S2 数据生命周期
- S2 的唯一主链路状态机是 `file bytes / structure -> parser._parse_raw -> BaseParser.parse(finalize) -> ParsedDocument -> Chunker -> index consumers`。
- 具体 parser 只负责“提取原始结构文本”，不再各自定义最终 `parse_status` 收口策略。
- `BaseParser.parse()` 是 S2 最终解析契约的唯一 owner；`ParserRegistry.parse()` 只负责格式路由和失败隔离，不再二次 finalize，也不再自己定义空正文语义。

### 统一 ParsedDocument 契约
- `ParsedDocument` 统一承载 `file_type / raw_text / title / parse_status / ParseError / paragraphs / page_count / metadata`。
- 解析失败现在返回可审计的结构化 `ParseError`，不再只靠字符串消息区分错误类型。
- 空文件、空白文件和“无可提取正文”的文件都统一落入失败桶，调用入口不同也不会得到不同状态。

### 四类解析器边界
- TXT：按空段落分段，输出稳定字符 offset。
- Markdown：支持标题层级、Setext 标题、围栏代码块规避、frontmatter 元数据提取。
- DOCX：提取段落、标题路径、表格、超链接文本、换行和 tab，不再在归一化阶段丢掉结构性控制字符。
- PDF：仅处理文字层，保留页码；若存在空文本页或后备 backend，则使用 `partial` 并记录结构化错误。

### Chunker 契约
- chunk 同时保留 `char / page / paragraph / heading_path` 定位信息。
- 无段落结构但有文本的文档，不再伪造 `paragraph_start=0 / paragraph_end=0`，而是显式 `None`。
- 重叠比例维持在 10% 到 15% 范围内，且不会跨 heading/page 边界泄漏语义。

## 3. 运行命令

```bash
# S2 阶段规定命令
./.venv/bin/pytest tests/unit/parsers -q
./.venv/bin/pytest tests/unit/indexing/test_chunker.py -q

# S2 acceptance_refs 映射验证
./.venv/bin/pytest tests/integration/indexing/test_full_index.py::TestTC001 -q
./.venv/bin/pytest tests/integration/indexing/test_full_index.py::TestTC002 -q
```

## 4. 测试结果

- `./.venv/bin/pytest tests/unit/parsers -q`：通过
- `./.venv/bin/pytest tests/unit/indexing/test_chunker.py -q`：通过
- `./.venv/bin/pytest tests/integration/indexing/test_full_index.py::TestTC001 -q`：通过
- `./.venv/bin/pytest tests/integration/indexing/test_full_index.py::TestTC002 -q`：通过

补充说明：
- 已显式验证 direct parser 与 `ParserRegistry.parse()` 对空文件产出完全一致的 `ParsedDocument`，不再存在双状态机分叉。

## 5. 已知问题 / 风险

| 问题 | 严重度 | 说明 |
|------|--------|------|
| 归一化 offset 仍对应归一化后文本，而非原始字节偏移 | 中 | 这是 `S2audit.md` 已登记债务，后续证据跳转如需严格原文字符映射，应在 S4/S9 建立原文 offset 映射层 |

## 6. 出口条件判定

| 出口条件 | 判定 | 依据 |
|---------|------|------|
| 四类文档均可解析 | **通过** | `tests/unit/parsers -q` 通过，覆盖 txt/md/docx/pdf |
| 失败文件不会拖垮批任务 | **通过** | `TestTC002` 通过 |
| chunk 保留定位信息且语义边界基本完整 | **通过** | `tests/unit/indexing/test_chunker.py -q` 通过 |

## 7. 迁移策略判定

- 本次采用：`低风险直接替换`
- 理由：
  - 项目仍处于开发阶段，无历史用户数据、无兼容包袱
  - S2 现有实现可复用，但必须收口旧的双 finalize 路径、空正文双语义路径和伪段落定位语义
- 复用：
  - 现有 `ParsedDocument`、四类 parser、`Chunker`、S2 单测骨架
- 旁路新建：
  - 无
- 收口旧实现：
  - 旧的“具体 parser 一套、registry 再补一套”解析状态机已收口为单一 owner

## 8. 下一阶段计划

S3：扫描、全量索引与增量更新
- 只消费 S2 当前统一的 `ParsedDocument` 与 chunk 契约
- 不重新定义 parser 状态语义

## 9. 2026-04-09 根因修复与签收收口

- **修复**：把 parser 最终收口职责统一收回到 `BaseParser.parse()`，具体 parser 改为 `_parse_raw()` 模式；`ParserRegistry.parse()` 退回为纯路由和失败隔离 owner。
- **修复**：收掉 direct parser 与 registry 在 `0` 字节文件、空白文件、无可提取正文上的状态机分叉；现在统一落成 `failed / no_extractable_text`。
- **修复**：`normalize_text()` 不再把 DOCX 提取出的 `tab` 静默改写为空格，结构性控制字符的语义边界恢复正确。
- **修复**：`Chunker` 对无段落文本不再伪造第 0 段定位。
- **治理补齐**：补充本阶段正式完成报告，并通过阶段报告契约测试把 owner 快照与状态机描述固定下来，避免“证据有了但阶段状态长期悬空”的治理漂移。
