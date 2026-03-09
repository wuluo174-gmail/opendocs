# S2 审计记录

## 审查与修复日志

**日期**：2026-03-08
**审查来源**：`.issues_found.md`（代码审查产出，共 6 项问题）
**审查范围**：S2 阶段解析器（txt/md/docx/pdf）、切片器、编码检测、文本归一化

---

### 问题 #1：UTF-8 BOM 未剥离

- **严重度**：中
- **文件**：`src/opendocs/parsers/_encoding.py:33`
- **问题**：使用 `raw.decode("utf-8")` 解码 UTF-8 文件不会去除 BOM（EF BB BF），导致首段文本开头带有不可见的 U+FEFF 字符。
- **修复**：将 `raw.decode("utf-8")` 改为 `raw.decode("utf-8-sig")`，Python 内置自动剥离 BOM。
- **新增测试**：`tests/unit/parsers/test_encoding.py::TestReadTextWithFallback::test_utf8_bom_stripped`
- **状态**：✅ 已修复，测试通过

---

### 问题 #2：带缩进的代码围栏关闭标记未识别

- **严重度**：中
- **文件**：`src/opendocs/parsers/md_parser.py:12`
- **问题**：`_FENCE_RE` 正则 `r"^(\`{3,}|~{3,})"` 要求围栏字符在行首第 0 列。CommonMark 允许关闭围栏前有 0–3 个空格，导致带缩进的关闭围栏不被识别，`in_fence` 永远不重置。
- **修复**：正则改为 `r"^ {0,3}(\`{3,}|~{3,})"`。
- **新增测试**：`tests/unit/parsers/test_md_parser.py::TestMdParser::test_indented_closing_fence`
- **状态**：✅ 已修复，测试通过

---

### 问题 #3：Setext 风格标题未识别

- **严重度**：低
- **文件**：`src/opendocs/parsers/md_parser.py`
- **问题**：仅支持 ATX 风格标题（`# Heading`），不支持 Setext 风格（`===` / `---` 下划线）。部分 Markdown 文件使用此格式，导致标题被当作普通段落。
- **修复**：新增 `_SETEXT_H1_RE` 和 `_SETEXT_H2_RE` 正则，在解析循环中检测 Setext 下划线行，将前一行缓冲内容提升为标题。
- **新增测试**：`test_setext_h1`、`test_setext_h2`
- **状态**：✅ 已修复，测试通过

---

### 问题 #4：ATX 标题尾部关闭哈希未去除

- **严重度**：低
- **文件**：`src/opendocs/parsers/md_parser.py:87`
- **问题**：CommonMark 允许 `# Heading ##` 格式，尾部的 `##` 应被去除。`.strip()` 仅去除空白。
- **修复**：新增 `_TRAILING_HASHES_RE`，在提取 heading_text 后用 `re.sub` 去除尾部哈希。
- **新增测试**：`test_atx_trailing_hashes_stripped`
- **状态**：✅ 已修复，测试通过

---

### 问题 #5：Chunker 未显式检查 parse_status

- **严重度**：低
- **文件**：`src/opendocs/indexing/chunker.py:123-125`
- **问题**：对 `parse_status == "failed"` 的文档，仅依赖隐含约定（空 `raw_text`）返回空结果。若未来解析器产生 `failed` 但 `raw_text` 非空的文档，切片器仍会产出 chunk。
- **修复**：在 `chunk()` 方法入口处添加显式检查 `if doc.parse_status == "failed": return []`。
- **新增测试**：`test_chunk_failed_document_with_nonempty_raw`
- **状态**：✅ 已修复，测试通过

---

### 问题 #6：DocxParser failed_paras 索引语义不一致

- **严重度**：低
- **文件**：`src/opendocs/parsers/docx_parser.py:67-68`
- **问题**：`para_idx` 计数所有 XML `w:p` 元素（含空段落），但最终 `Paragraph.index` 来自 `enumerate(entries)`（仅含非空段落）。错误信息中的索引无法与输出对应。
- **修复**：将 `failed_paras.append(para_idx)` 改为 `failed_paras.append(len(entries))`，记录输出段落索引。原 `para_idx` 重命名为 `xml_para_idx` 以明确语义。
- **状态**：✅ 已修复，测试通过

---

---

### 问题 #7：不支持格式的 file_type 回退值为 "txt"

- **严重度**：低
- **文件**：`src/opendocs/parsers/base.py:116`
- **问题**：`ext_to_type.get(ext, "txt")` 对不支持的格式（如 `.doc`）默认返回 `file_type="txt"`。`ParsedDocument.file_type` 的 Literal 约束只允许 `txt/md/docx/pdf`，无法表达 `"unknown"`。
- **修复**：添加注释说明这是有意设计——结果已标记 `parse_status="failed"` 且 `error_info` 携带真实扩展名，下游应先检查 `parse_status`。
- **状态**：✅ 已处理（添加文档注释）

---

### 问题 #8：ChunkResult 与 S1 ChunkModel 无跨层字段映射验证

- **严重度**：低
- **文件**：`tests/unit/indexing/test_chunker.py`
- **问题**：`ChunkResult`（S2）的字段应与 `ChunkModel`（S1 ORM）一一对应，但无测试守护。如果 S1 改名或删除列，S3 写入时才会报错。
- **修复**：新增 `TestChunkResultToChunkModelMapping` 测试类，断言两者字段集合对齐。
- **新增测试**：`test_all_chunk_fields_present_in_orm`
- **状态**：✅ 已修复，测试通过

---

## 已知债务（须在后续阶段解决）

### DEBT-01：偏移量对应归一化文本，FR-015 证据跳转需额外映射

- **关联**：ADR-0010、FR-015、TC-018
- **现状**：`ParserRegistry.parse()` 归一化后用 `"\n".join(parts)` 重建 `raw_text`，`char_start/end` 对应归一化后的文本，而非原始文件字节偏移。
- **影响**：到 S9 TC-018 需要"引用面板跳转到原始文件段落/字符区间"时，当前偏移量无法直接用于定位原文。
- **建议解决时机**：S4（证据定位）或 S9（UI 引用跳转）
- **建议方案**：在 `ParserRegistry.parse()` 中保留原始偏移映射（`original_start_char` / `original_end_char`），或在证据定位层做二次映射。

### DEBT-02：overlap 导致 chunk.text 与 char_start:char_end 不对称

- **关联**：§8.3、S3 FTS 索引
- **现状**：有重叠时，`chunk.text = overlap_prefix + "\n" + new_content`，但 `char_start:char_end` 只覆盖 new_content。`doc.raw_text[char_start:char_end] ≠ chunk.text`。
- **影响**：S3 构建 FTS 索引时，若直接用 `chunk.text`，重叠文本会被重复索引，影响 FTS 评分权重。
- **建议解决时机**：S3（FTS 写入时决定索引 text 还是 body-only text）
- **建议方案**：S3 写入 FTS 时使用 `doc.raw_text[chunk.char_start:chunk.char_end]` 作为索引文本，`chunk.text` 仅用于向量嵌入和展示。

---

## 测试验证

```
$ python -m pytest tests/ -v
244 passed in 2.03s
```

全部 244 个测试通过，零回归。新增测试 6 个，覆盖所有 6 项修复。

**二次审查补充（2026-03-08）**：新增 1 个跨层映射测试，验证 ChunkResult 与 ChunkModel 字段对齐。

---

## 三次审查修复（2026-03-09）

**审查来源**：`.issues_found.md`（代码审查产出，共 3 项问题）

### 问题 #9：DocxParser 超链接/修订标记内的文字被静默丢弃

- **严重度**：中
- **文件**：`src/opendocs/parsers/docx_parser.py:60`
- **问题**：`child.findall(qn("w:r"))` 只返回 `w:p` 的直接子元素 `w:r`，不会递归进入 `w:hyperlink`、`w:ins`、`w:del` 等容器节点。包含超链接或修订追踪的 DOCX 文件，链接文字和修订内容被静默丢弃。
- **修复**：将 `child.findall(qn("w:r"))` 改为 `child.iter(qn("w:r"))`，遍历所有后代节点中的 `w:r`。
- **新增测试**：`tests/unit/parsers/test_docx_parser.py::TestDocxParser::test_hyperlink_text_not_lost`
- **新增 fixture**：`conftest.py::tmp_docx_with_hyperlink`
- **状态**：✅ 已修复，测试通过

---

### 问题 #10：PdfParser TOC 排序键破坏同页条目的文档顺序

- **严重度**：低
- **文件**：`src/opendocs/parsers/pdf_parser.py:130`
- **问题**：以 `(page_no, level)` 排序会把同一页上的 TOC 条目按 level 重新排列，破坏 PDF 书签的原始文档顺序。
- **修复**：仅按 `page_no` 排序，利用 Python 排序的稳定性保留原始顺序。
- **新增测试**：`tests/unit/parsers/test_pdf_parser.py::TestPdfParser::test_toc_same_page_preserves_document_order`
- **状态**：✅ 已修复，测试通过

---

### 问题 #11：PdfParser fitz 文档句柄在异常时泄漏

- **严重度**：低
- **文件**：`src/opendocs/parsers/pdf_parser.py:44,63`
- **问题**：`fitz.open()` 和 `doc.close()` 之间的代码如果抛出异常，文件句柄不会被关闭。
- **修复**：使用 `with fitz.open(str(file_path)) as doc:` 上下文管理器。
- **状态**：✅ 已修复，测试通过

---

### 测试验证

```
$ python -m pytest tests/ -v
251 passed in 2.15s
```

全部 251 个测试通过，零回归。新增测试 2 个，覆盖问题 #9 和 #10。

### 三次审查修改文件清单

| 文件 | 变更类型 |
|------|----------|
| `src/opendocs/parsers/docx_parser.py` | 修改（findall → iter，捕获超链接/修订内文字） |
| `src/opendocs/parsers/pdf_parser.py` | 修改（TOC 排序键去除 level；fitz 句柄改用 with） |
| `tests/unit/parsers/conftest.py` | 新增 fixture `tmp_docx_with_hyperlink` |
| `tests/unit/parsers/test_docx_parser.py` | 新增 1 个测试 |
| `tests/unit/parsers/test_pdf_parser.py` | 新增 1 个测试 |

---

## 修改文件清单（首次审查）

| 文件 | 变更类型 |
|------|----------|
| `src/opendocs/parsers/_encoding.py` | 修改（utf-8 → utf-8-sig） |
| `src/opendocs/parsers/md_parser.py` | 修改（围栏正则、Setext 支持、尾部哈希） |
| `src/opendocs/indexing/chunker.py` | 修改（显式 parse_status 检查） |
| `src/opendocs/parsers/docx_parser.py` | 修改（failed_paras 索引语义） |
| `src/opendocs/parsers/base.py` | 修改（不支持格式 file_type 回退注释） |
| `tests/unit/parsers/test_encoding.py` | 新增 1 个测试 |
| `tests/unit/parsers/test_md_parser.py` | 新增 4 个测试 |
| `tests/unit/indexing/test_chunker.py` | 新增 2 个测试（parse_status + 跨层映射） |
