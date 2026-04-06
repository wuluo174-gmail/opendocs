# S4 阶段完成报告：混合检索与证据定位

## 1. 新增/修改文件列表

本节只记录当前仓库中仍然存在、且仍由 S4 主链路消费的 owner / 交付物快照。历史 helper、已删除路径和迁移前实现只能写入后续修复记录，不能继续冒充当前交付物。

### 新增源码（S4 主体）
- `src/opendocs/app/search_service.py` — SearchService 搜索、证据定位、打开文件入口
- `src/opendocs/retrieval/search_pipeline.py` — FTS + dense + freshness 融合主链路
- `src/opendocs/retrieval/evidence.py` — 统一 Citation / SearchResult / SearchResponse 结构
- `src/opendocs/retrieval/evidence_locator.py` — 引用定位与文件打开
- `src/opendocs/retrieval/filters.py` — 六维预过滤
- `src/opendocs/retrieval/fts_searcher.py` — trigram FTS 检索
- `src/opendocs/retrieval/dense_searcher.py` — dense 检索
- `src/opendocs/retrieval/query_preprocessor.py` — 查询归一化与 FTS 安全清洗
- `src/opendocs/retrieval/rerank.py` — 分数归一化与融合
- `src/opendocs/retrieval/embedder.py` — 本地离线 embedder

### 本轮收口新增/修改（根因修复 + 回归）
- `src/opendocs/storage/schema/0004_index_artifacts.sql` — dense 工件状态表
- `src/opendocs/storage/schema/0006_documents_directory_facts.sql` — 目录过滤显式事实字段
- `src/opendocs/storage/repositories/index_artifact_repository.py` — dense 工件状态仓储
- `src/opendocs/indexing/hnsw_manager.py` — DB-backed dense 工件状态机 + 启动修复 + 过滤后精确 post-filter
- `src/opendocs/indexing/index_builder.py` — 在 SQLite 事务内标记 dense stale，并同步旧 chunk 的 HNSW 删除
- `src/opendocs/app/index_service.py` — 显式补偿重建原因
- `src/opendocs/retrieval/stage_golden_queries.py` — S4 阶段黄金查询资产加载与校验
- `src/opendocs/retrieval/stage_filter_cases.py` — S4 过滤组合资产加载与校验
- `src/opendocs/retrieval/stage_acceptance_corpora.py` — S4 验收语料 owner 加载与校验
- `src/opendocs/retrieval/stage_acceptance_capture_cases.py` — S4 验收截图选择资产加载与校验
- `src/opendocs/retrieval/stage_acceptance_provenance.py` — S4 工件输入 provenance owner
- `src/opendocs/retrieval/stage_search_corpus.py` — S4 搜索验收语料生成器
- `src/opendocs/acceptance/s4_capture_harness.py` — TC-005 / TC-018 验收工件的固定生成逻辑与 acceptance runtime 编排
- `scripts/capture_s4_tc005_artifacts.py` — TC-005 工件生成入口
- `scripts/capture_s4_tc018_artifacts.py` — TC-018 工件生成入口
- `docs/acceptance/artifacts/README.md` — 验收工件固定归档约定

### 测试
- `tests/unit/retrieval/` — embedder / filters / evidence / rerank / search_pipeline / FTS 单元回归
- `tests/integration/search/test_hybrid_search.py` — dense-only、混合检索、旧索引修复、同维度签名漂移修复
- `tests/integration/search/test_filter_combinations.py` — 六维过滤组合回归
- `tests/integration/search/test_citation_accuracy.py` — 引用路径、char range、quote preview、locate_evidence
- `tests/integration/search/test_cli_smoke.py` — CLI 搜索与 `--open` 分支

## 2. 关键实现说明

### 混合检索主链路
- 使用 `trigram FTS + dense HNSW + freshness` 做融合，满足 ADR-0012 的短词 dense 补偿要求。
- 搜索结果统一输出标题、路径、摘要、时间、分数拆解和引用结构。

### 验收工件 owner 与生命周期
- `src/opendocs/acceptance/s4_capture_harness.py` 是 S4 验收工件生成的唯一 runtime owner；状态流转固定为 `stage assets -> acceptance runtime (SQLite/HNSW) -> SearchService -> SearchWindow -> artifacts/manifest`。
- `opendocs.ui` 只保留可复用部件，不再拥有 DB/file runtime bootstrapping；`TC-005/TC-018` 的脚本、测试、阶段文档和归档工件因此对齐到同一条 owner 链。

### 引用与打开
- 引用对象包含 `path / page_or_paragraph / char_range / quote_preview`，但机器定位值与用户展示值现在已拆开：存储层保留 0 基段落索引，对外统一转成 1 基段落号。
- `SearchService.load_evidence_preview()` + 最小 UI 壳新增应用内预览定位链路；引用点击现在优先走本地解析后的预览定位，不再把“外部默认应用是否理解 URI 片段”当成定位能力本身。
- `SearchService.open_document()` 保留为打开文件的辅助动作；`SearchService.reveal_document()` 新增“打开所在目录”动作，对齐 FR-003。
- `TC-005` 的查询与结果日志、引用点击截图现在也有固定工件链路；固定命令会用阶段 acceptance corpus owner、黄金查询资产、过滤组合资产和 capture 选择资产产出截图、`query_results.json` 和 `manifest.json`，截图文件名也不再在脚本里重复声明，而是从 capture 资产派生后输出到 `docs/acceptance/artifacts/s4/tc005/`。
- `TC-018` 的截图留痕不再依赖人工临时截屏；现在有固定命令从阶段 acceptance corpus owner 和 capture 选择资产读取固定语料、截图选择规则、页码/段落语义和输出文件名，把 PDF 定位截图、无页码段落定位截图和 `manifest.json` 输出到 `docs/acceptance/artifacts/s4/tc018/`。
- 两类 manifest 现在都会显式记录输入资产 provenance，而且 provenance policy 本身也收回到 retrieval 层，由 acceptance harness 只负责 runtime 编排与写出；这样 `TC-005/TC-018` 的工件能直接回溯到对应的 stage assets。

### 过滤正确性修复
- 修复了 `time_range` 过滤使用 ISO `T` 格式导致 SQLite 文本比较失真的问题，统一改为 SQLite 兼容时间格式。
- 修复了过滤 dense 查询会退化成全索引扫描的问题；现在无过滤时走 HNSW ANN，有过滤时直接在 `HnswManager` 管理的向量 sidecar 上对子集做精确打分，保证“过滤后仍返回可引用片段”且不会为了过滤把 `k` 提升到全索引规模。
- 目录过滤不再对 `path/relative_path` 做运行时字符串替换；现在直接消费 SQLite 中的 `directory_path / relative_directory_path` 权威字段，输入前缀只做一次规范化。

### dense 一致性根因修复
- `index_artifacts` 作为 SQLite 中的权威工件状态表，记录 dense 索引的路径、embedder、签名和状态。
- `SearchService` 启动修复不再只看 dirty flag，还会校验 DB 工件状态、签名、路径与磁盘工件健康度；旧 64 维或同维度签名漂移都会触发重建。

## 3. 运行命令

```bash
# S4 单元测试
./.venv/bin/pytest tests/unit/retrieval -q

# S4 集成测试
./.venv/bin/pytest tests/integration/search -q

# TC-005 工件归档
./.venv/bin/python scripts/capture_s4_tc005_artifacts.py --force

# TC-018 工件归档
./.venv/bin/python scripts/capture_s4_tc018_artifacts.py --force

# 相关存储/一致性回归
./.venv/bin/pytest tests/unit/storage/test_schema_consistency.py tests/unit/storage/test_migrations.py -q
```

## 4. 测试结果

- `tests/unit/retrieval -q`：通过
- `tests/integration/search -q`：通过
- `tests/unit/storage/test_schema_consistency.py tests/unit/storage/test_migrations.py -q`：通过
- 额外回归：
  - `tests/integration/indexing/test_rebuild_idempotent.py -q`：通过
  - `tests/integration/indexing -q`：通过
  - `scripts/rebuild_index.py --source tests/fixtures/generated/corpus_main`：通过，输出为 `Rebuild complete: 9 success, 2 failed, 0 skipped, hnsw=synced`
  - `scripts/capture_s4_tc005_artifacts.py --force`：通过，工件归档到 `docs/acceptance/artifacts/s4/tc005/`
  - `scripts/capture_s4_tc018_artifacts.py --force`：通过，工件归档到 `docs/acceptance/artifacts/s4/tc018/`

## 5. 已知问题 / 风险

| 问题 | 严重度 | 说明 |
|------|--------|------|
| 不同系统对 PDF `#page=` 片段的支持不完全一致 | 中 | 当前实现已保留并透传定位参数，PDF 页码跳转采用 best-effort URI fragment；打开文件本身和定位元数据展示均已可验证 |

## 6. 出口条件判定

| 出口条件 | 判定 | 依据 |
|---------|------|------|
| S4 阶段黄金查询集通过率达标 | **通过** | `src/opendocs/retrieval/assets/s4_hybrid_search_queries.json` 的 `test_regression_top10_hit_rate` 通过 |
| UI 或 CLI 可展示引用结果 | **通过** | `tests/integration/search` 与 CLI smoke 通过 |
| 至少能打开文件所在位置 | **通过** | `SearchService.reveal_document()`、`Reveal Folder` UI 动作与 `tests/integration/search/test_evidence_panel_ui.py` 通过；`open_document()` / CLI `--open` 作为辅助打开动作也通过 |

## 7. 下一阶段计划

S5：问答、摘要与洞察
- RAG 问答与证据包
- 引用校验器
- 证据不足拒答
- 冲突检测
- 多文档摘要与洞察导出

## 8. 2026-03-20 审查修复

- **修复**：`SearchService.open_document()`、`SearchWindow`、CLI `search --open` 现在都会把 `page_no / paragraph_range / char_range` 透传到 `EvidenceLocator.open_file()`，不再只传裸路径。
- **修复**：`EvidenceLocator.open_file()` 对 PDF 页码增加 best-effort `#page=` 打开目标，至少保证定位提示不会在打开链路里丢失。
- **修复**：新增应用内证据预览定位器，引用点击会重新解析本地文件并在 UI 内高亮证据片段；外部打开文件退回成辅助动作，不再冒充“定位已完成”。
- **修复**：新增 `reveal_document()` / `Reveal Folder`，补齐“打开所在目录”能力。
- **修复**：内部 0 基 `paragraph_start/end` 不再直接泄漏到引用/UI，对外统一展示为 1 基段落号。
- **修复**：目录过滤改为 DB-backed 根因修复；`SearchFilter.directory_prefixes` 通过 `directory_path / relative_directory_path` 查询，支持相对目录与绝对目录两种输入。
- **修复**：S4 Top10 检索 gate 的数据集从普通 fixture 回归查询中分离，改为 `src/opendocs/retrieval/assets/s4_hybrid_search_queries.json` 作为阶段黄金集，消除阶段报告口径漂移。
- **修复**：`TC-018` 验收留痕从“人工临时截图”改成固定脚本产物，仓库内现已归档 PDF / 无页码两类引用定位截图与 `manifest.json`。
- **测试**：更新 pytest-qt、检索集成测试和定位精度测试，覆盖应用内定位、打开文件、打开目录、1 基段落号和阶段黄金集。

## 9. 2026-03-22 同义词数据边界补充修复

- **修复**：词表导入边界现在显式拒绝“expansion 在归一化后等于 trigger_query”的坏数据；不再允许 `QueryPreprocessor` 在运行时静默去重来掩盖数据问题。
- **修复**：expansion 的唯一性校验与 trigger 统一为同一套 `normalize + casefold` 语义；`AI/ai` 这类只差大小写的重复项现在会在导入边界直接报错。
- **修复**：`QueryPreprocessor._expand_variants()` 不再承担词表清洗职责；当前实现直接消费已校验的规范化词表，消除了下游擦屁股分支。
- **修复**：S4 黄金查询资产从 `tests/` 下的临时数据收回到 retrieval 受控资产层，改成 `src/opendocs/retrieval/assets/s4_hybrid_search_queries.json` + 共享加载器；测试与验收工件现在消费同一个 owner。
- **修复**：S4 搜索验收语料不再由集成测试和工件脚本各自维护，改成 `src/opendocs/retrieval/stage_search_corpus.py` 统一生成；`TC-005` 工件与搜索集成测试现在消费同一个 corpus owner。
- **修复**：新增 `TC-005` 固定工件链路，查询与结果日志、引用点击截图和 `manifest.json` 都能用同一条命令重复生成。
- **修复**：`TC-005` 的 3 组过滤组合输入从集成测试代码中收回到 `src/opendocs/retrieval/assets/s4_search_filter_cases.json`；过滤组合测试和 `TC-005` 工件日志现在消费同一个 owner。
- **修复**：`TC-005/TC-018` 的截图选择规则不再散落在早期临时 capture helper 的代码常量里，改成 `src/opendocs/retrieval/assets/s4_acceptance_capture_cases.json` + 共享加载器；测试、工件脚本和阶段文档现在消费同一个 capture owner。
- **修复**：`TC-005/TC-018` 的 planned outputs 不再手写文件名列表；现在由 capture 资产的 slug 统一派生。`TC-018` 的页码型 / 段落型语义也成为资产字段，不再让测试用硬编码文件名反推。
- **修复**：`TC-005/TC-018` 的默认 acceptance corpus 不再由早期临时 capture helper 自己决定；现在统一改成 `src/opendocs/retrieval/assets/s4_acceptance_corpora.json` + 共享 loader，`TC-005` 的 manifest 标签和 `TC-018` 的 fixture 路径都由同一个 corpus owner 派生。
- **修复**：`scripts/capture_s4_tc018_artifacts.py` 不再用 argparse 默认值把“未传 corpus_dir”和“显式传默认路径”混成一类；现在默认命令生成的 `manifest.generator_command` 不再硬编码机器本地绝对路径。
- **修复**：`TC-005` 的默认工件命令也收紧到同一语义：默认 acceptance corpus 由 stage owner 决定，`manifest.generator_command` 不再允许偷偷带上默认 `--corpus-dir`。
- **修复**：`TC-005/TC-018` 的 manifest 新增输入资产 provenance，显式指向 acceptance corpus / capture cases / golden queries / filter cases / corpus builder 这些 stage owners，补齐最后一段审计链路。
- **修复**：manifest provenance 的 owner 不再是早期临时 capture helper 内部 helper，改成 `src/opendocs/retrieval/stage_acceptance_provenance.py`；集成测试现在对齐 retrieval 层 owner，而不是对齐 UI 实现本身。
- **修复**：S4 runtime synonym lexicon 不再由 acceptance golden queries 反向 owning；当前运行时词表改成 retrieval 自己拥有的 `src/opendocs/retrieval/assets/query_lexicon.json` 对等别名簇，golden queries 只验证批准子集，`TC-005` 仍保持 `5 条定位 + 5 条同义 + 1 条零结果`，这样运行时能力可以在同一 stage 内做受控扩展，而不是被验收资产硬编码锁死。
- **修复**：`TC-005` 的 manifest provenance 现在显式包含 runtime 同义词词表资产 `src/opendocs/retrieval/assets/query_lexicon.json`；这样同义查询命中能力的真正输入 owner 也能被工件直接审计，不再只看到 golden queries 而看不到底层 lexicon。
- **修复**：`SearchFilter` 不再把 source root 和 directory prefix 混成同一维度；当前模型拆成 `source_roots + directory_prefixes` 两层，SQL 组合语义恢复为跨维度 `AND`、同维度 `OR`。CLI 的 `--root/--dir` 和 UI 的 `Root/Dir` 输入边界也同步拆开，`display_root` 与根目录绝对路径现在都能作为 root filter 生效。
- **修复**：retrieval 层的所有 stage asset loader 现在都通过共享的 `stage_asset_loader.py` 从 `*_ASSET_REF` 常量反解运行时资源路径；运行时代码和 manifest provenance 不再各写一套文件名字符串，消除了“声明的 owner”和“实际读取的 owner”再度分叉的风险。
- **修复**：`stage_asset_loader.py` 现在显式拒绝带 `.` / `..` 的 asset ref 路径穿越；`*_ASSET_REF` 不再只是“看起来像在 asset root 下”，而是运行时也必须真的留在该根目录里。
- **修复**：`S4` deterministic search corpus 的文档集合现在成为显式 owner；黄金查询和过滤组合在加载边界就会校验 `expect_doc` 是否属于 `stage_search_corpus.py` 声明的文档路径，避免资产引用脏数据时只能靠搜索结果碰运气。
- **修复**：删除仓库内未被主链路使用的 `tests/fixtures/search_regression_queries.yaml`；`S4` 检索输入不再保留第二份遗留 owner，当前唯一权威来源只剩 retrieval 层的阶段资产与共享 loader。
- **修复**：`S4` search environment 不再只拥有“文件语料”而偷偷依赖另一份默认 source metadata；`tests/integration/search/conftest.py` 和 `TC-005` 工件生成现在共同消费 `stage_search_corpus.py#source_defaults`，`shared-source` 这类标签不再是某一条运行时路径私有的补丁数据。
- **修复**：`stage_search_corpus.py` 现在不只声明文件列表，还会通过真实 parser 路径推导每个文档的有效搜索画像；`stage_filter_cases.py` 在加载边界就会校验目录、分类、标签、文件类型、敏感级和时间范围是否真的能命中 `expect_doc`，不再把脏 filter 资产拖到集成搜索阶段才暴露，也不再假设 parser 语义永远和 spec 声明一致。
- **修复**：`build_s4_search_document_profiles()` 不再把带缓存的可变 `dict` / `DocumentMetadata` 直接暴露给下游；当前实现把缓存收回私有边界，对外每次都返回新拷贝，避免任何调用方污染共享 stage 文档画像后反向影响 filter 校验与验收工件。
- **测试**：新增词表解析与预处理器回归，覆盖“trigger 与 expansion 冲突必须报错”的场景。

## 10. 2026-04-02 引用副作用状态机修复

- **根因**：`EvidenceLocator.resolve_open_target()` 把“证据记录不存在”和“目标文件已丢失”都压成 `None`，导致 `SearchService.open_evidence()` 只能返回同一种失败语义；CLI 也把“外部打开请求已发起”错误地展示成“已经打开”。
- **修复**：`resolve_open_target()` 只负责解析 citation owner，不再替外部副作用层吞掉 `missing_target`；文件是否存在继续由 `open_file()` / `reveal_in_file_manager()` 作为副作用 owner 返回结构化状态。
- **修复**：`SearchWindow` 的 locate 状态现在同时显示“预览是否就绪”和“外部打开请求结果”，显式区分本地证据预览与外部打开副作用。
- **修复**：CLI `search --open` 文案改成 `Open request launched`，不再把子进程成功拉起伪装成“文件已经打开”。
- **测试**：`tests/integration/search/test_cli_smoke.py` 和 `tests/integration/search/test_evidence_panel_ui.py` 新增/更新结构化结果断言，覆盖 launched / launch_failed / unresolved_evidence / missing_target 四种状态。

## 11. 2026-04-06 S4 dense 归一化与验收工件 owner 修复

- **根因**：dense 通道之前没有自己的文本归一化 owner。query preprocessor 负责了一部分查询归一化，但 embedder 在索引态和查询态都直接消费原始文本，导致 `AI / ai` 这类只差大小写的短英文查询在 dense-only 场景下分裂成两套语义。
- **修复**：`LocalNgramEmbedder` 现在把 `normalize_text + casefold + strip` 收回到自身边界，查询向量和 chunk 向量都先经过同一条归一化链，再进入 n-gram hash；dense 语义不再依赖调用方碰巧传入什么大小写。
- **修复**：embedder 模型签名升级为 `local-ngram-hash-v2`。旧 dense 工件会通过既有的签名校验与重建路径自动失效，避免把旧语义向量误当成新语义继续复用。
- **修复**：`src/opendocs/acceptance/s4_capture_harness.py` 的默认工件目录根路径改为仓库根目录，不再把 `src/opendocs` 误认成 repo root；`TC-005/TC-018` 的默认脚本输出重新对齐到 `docs/acceptance/artifacts/s4/...` 这条受控生命周期。
- **测试**：补充 `tests/unit/retrieval/test_embedder.py` 的大小写/全角归一化回归，更新 `tests/integration/search/test_hybrid_search.py` 覆盖 `AI / ai / ＡＩ` 三个短英文变体，并在 `tests/unit/retrieval/test_s4_stage_report_contract.py` 中固化默认工件目录必须落在仓库级 `docs/acceptance/artifacts/`。
