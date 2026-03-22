# ADR-0012: FTS5 trigram tokenizer + dense 通道短词补偿

## 状态

已接受（2026-03-20）

## 背景

ADR-0007 将 FTS5 中文分词方案延迟到 S3/S4 选定。S4 实施前经多轮评估和实测：

- `unicode61`（默认）：CJK 连续串作为整段单 token（如 `项目进度报告` → 单 token），非前缀子串不可搜
- `trigram`：3+ 字符子串匹配有效，1-2 字符查询无结果
- `simple`：当前 SQLite 环境不可用（OperationalError）
- ICU：需编译 C 扩展，跨平台打包复杂度高

FTS5 运算符大小写敏感：仅大写 `AND`/`OR`/`NOT` 是运算符，小写是普通 token。

## 决策

采用 **trigram tokenizer + HNSW dense 通道短词补偿**：

1. Schema 迁移 0003：将 `chunk_fts` 从默认 `unicode61` 改为 `tokenize='trigram'`
2. 保持 content-sync + triggers 模式不变（与 0001 同构）
3. 迁移末尾 `INSERT INTO chunk_fts(chunk_fts) VALUES('rebuild')` 自动回填
4. 3+ 字符查询走 trigram FTS（子串匹配 + BM25 排名）
5. < 3 字符查询（如"项目""AI"）FTS 天然无结果，由 HNSW dense 通道补偿
6. 整条查询原样传入两个通道，不拆分、不 UNION、不 LIKE
7. QueryPreprocessor 仅做归一化 + FTS5 语法安全清洗，不修改运算符

## 被否决的方案

| 方案 | 否决原因 |
|------|----------|
| `unicode61` + phrase query | CJK 连续串是整段 token，不是逐字符（实测确认） |
| `unicode61` + QueryPreprocessor | 同上，phrase query 前提错误 |
| `trigram` + LIKE 短词补充 | split+union 破坏查询 AND 语义；LIKE 对 ASCII 大小写不敏感有噪声 |
| `simple` tokenizer | 当前环境不可用 |
| jieba 预分词 + `simple` | `simple` 不可用 |
| ICU tokenizer | 需编译 C 扩展 |

## 影响

- 需要 schema 迁移 `0003_fts5_trigram_tokenizer.sql`
- 索引体积增大（trigram 为每段文本生成大量三字符组），对本地百级文档可接受
- < 3 字符查询的排名完全依赖 dense 通道（0.35 权重），在小语料上区分度足够
- FTS5 运算符大小写敏感是原生行为，不尝试修改

## 关闭

关闭 ADR-0007 的延迟状态。
