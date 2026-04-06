# 验收工件目录约定

本目录用于归档阶段验收需要保留的截图、录像、日志摘要和 manifest。

## 目录规则

- 按阶段和用例编号归档：`docs/acceptance/artifacts/<stage>/<case-id>/`
- 每个用例目录至少包含：
  - 可视化工件：截图或录像
- `manifest.json`：说明生成命令、输入语料和产出文件
- 默认不允许静默覆盖已有工件；重新生成时应显式传 `--force`

## S4 / TC-018

`TC-018` 的引用跳转工件固定归档到：

- `docs/acceptance/artifacts/s4/tc018/tc018_pdf_locate.png`
- `docs/acceptance/artifacts/s4/tc018/tc018_paragraph_locate.png`
- `docs/acceptance/artifacts/s4/tc018/manifest.json`

生成命令：

```bash
./.venv/bin/python scripts/capture_s4_tc018_artifacts.py --force
```

该命令使用仓库内固定语料 `tests/fixtures/generated/corpus_main`，并从阶段 capture
资产 `src/opendocs/retrieval/assets/s4_acceptance_capture_cases.json` 读取两张截图的选择规则、
定位语义以及输出文件名；默认情况下命令不需要显式传 `--corpus-dir`，而是直接使用
`src/opendocs/retrieval/assets/s4_acceptance_corpora.json` 声明的 stage corpus owner，自动生成：

- 一张 PDF 引用定位截图
- 一张无页码文档段落定位截图
- 一份工件 manifest，包含由 retrieval 阶段 owner 生成的输入资产 provenance

## S4 / TC-005

`TC-005` 的混合搜索验收工件固定归档到：

- `docs/acceptance/artifacts/s4/tc005/tc005_locating_results.png`
- `docs/acceptance/artifacts/s4/tc005/tc005_synonym_results.png`
- `docs/acceptance/artifacts/s4/tc005/query_results.json`
- `docs/acceptance/artifacts/s4/tc005/manifest.json`

生成命令：

```bash
./.venv/bin/python scripts/capture_s4_tc005_artifacts.py --force
```

该命令默认使用共享的 S4 搜索验收语料生成器
`src/opendocs/retrieval/stage_search_corpus.py`、阶段黄金查询资产
`src/opendocs/retrieval/assets/s4_hybrid_search_queries.json`、runtime 同义词词表资产
`src/opendocs/retrieval/assets/query_lexicon.json`、过滤组合资产
`src/opendocs/retrieval/assets/s4_search_filter_cases.json`、acceptance corpus 资产
`src/opendocs/retrieval/assets/s4_acceptance_corpora.json`，以及 capture 选择资产
`src/opendocs/retrieval/assets/s4_acceptance_capture_cases.json`。`TC-005` 的 search environment 还会显式应用
`src/opendocs/retrieval/stage_search_corpus.py#source_defaults` 声明的 source defaults，
这样搜索集成测试和工件生成不会再各自偷偷拥有一套默认元数据；默认语料标签、截图文件名与选择规则都由这些阶段资产派生，默认命令不需要显式传 `--corpus-dir`，自动生成：

- 两张引用点击后的搜索界面截图
- 一份覆盖全部黄金查询和 3 组过滤组合的查询与结果日志
- 一份工件 manifest，包含由 retrieval 阶段 owner 生成的输入资产 provenance
