# S5 阶段完成报告：问答、摘要与洞察

## 1. 新增/修改文件

### 新增源码
- `src/opendocs/app/qa_service.py`
- `src/opendocs/qa/models.py`
- `src/opendocs/qa/orchestrator.py`
- `src/opendocs/qa/citation_validator.py`
- `src/opendocs/qa/conflict_detector.py`
- `src/opendocs/qa/generator.py`
- `src/opendocs/qa/summarizer.py`
- `src/opendocs/qa/insight_extractor.py`
- `src/opendocs/qa/markdown_exporter.py`

### 修改源码
- `src/opendocs/app/__init__.py`
- `src/opendocs/app/search_service.py`
- `src/opendocs/qa/__init__.py`

### 新增测试
- `tests/integration/qa/conftest.py`
- `tests/integration/qa/test_answer_with_citations.py`
- `tests/integration/qa/test_insufficient_evidence.py`
- `tests/integration/qa/test_conflict_detection.py`
- `tests/integration/summary/conftest.py`
- `tests/integration/summary/test_multi_document_summary.py`
- `tests/unit/qa/test_citation_validator.py`

### 新增文档
- `docs/test-plan/S5_stage_report.md`

## 2. 关键实现说明

### 查询计划与证据包
- 将“问题类型”和“请求的事实槽位”上升为正式数据结构：`QueryPlan` 持有 `intent / subject_terms / requested_fact_keys / requested_insight_kinds`。
- 将证据中的结构化事实上升为 `FactRecord`，并在 `EvidenceItem` 中持久携带，不再让生成器、冲突检测器、校验器各自重新猜一次。

### QAService 主链路
- `QAService.answer()` 现在按 `fact / summary / compare / timeline` 四条路径分流，不再把所有问题硬塞进同一套事实问答流水线。
- `summary` 路径优先走 `InsightExtractor / SummaryComposer`；`compare` 路径展开多来源差异；`timeline` 路径按文档时间排序；`fact` 路径仍走受控事实抽取 + 引用校验。

### 引用校验与拒答
- 引用校验器从“词项重叠”改成“结构化 key/value 对齐”：同 key 不同 value 一律不算支持证据。
- 这修复了“问合同编号却回答负责人”和“相反发布日期也被当成支持”的根因问题。
- 当请求槽位在证据中不存在时，统一降级为“当前证据不足以可靠回答该问题”模板。

### 冲突检测
- 冲突检测不再靠正则和散乱关键词猜测，而是直接对 `requested_fact_keys` 下的 `FactRecord` 做同 key / 不同 value 聚合。
- 冲突回答至少展示两个来源，并保留 citation。

### 摘要、洞察与导出
- 多文档摘要与 `decision / risk / todo` 洞察继续保留 citation 追溯。
- Markdown 导出仍保持双阶段：先 `preview_markdown_export()`，再 `save_markdown_export(..., confirmed=True)`；默认拒绝无确认写入，也拒绝覆盖现有文件。

## 3. 运行命令

```bash
./.venv/bin/pytest tests/integration/qa -q
./.venv/bin/pytest tests/integration/summary -q
./.venv/bin/pytest tests/unit/qa/test_citation_validator.py -q
./.venv/bin/pytest -q
```

## 4. 测试结果

- `tests/integration/qa`：通过，覆盖事实问答附引用、同主题缺字段拒答、冲突展示、`compare / timeline` 分路径。
- `tests/integration/summary`：通过，覆盖多文档摘要、洞察提取、Markdown 预览与确认后导出。
- `tests/unit/qa/test_citation_validator.py`：通过，覆盖“同 key 不同 value”不得视为支持证据。
- `pytest -q`：通过，S0-S5 全量回归通过。
- 本阶段规定命令均已执行完成，无失败留存。

## 5. 已知问题/风险

- 当前 `S5` 仍是本地抽取式实现，目的是先守住“证据优先、证据不足拒答”的红线；真正的 provider 路由与网络模式仍在 `S10`。
- 当前摘要与洞察依赖显式模式词（如 `决策：`、`风险：`、`待办：`）；这是有意保持简单，避免在 `S5` 提前堆复杂模型逻辑。
- 记忆治理仍留在 `S8`，当前仅保留“记忆可能陈旧或错误”的冲突提示占位，不允许记忆参与事实裁决。

## 6. 出口条件判定

- [x] 事实问答默认附引用
- [x] 证据不足时不胡答
- [x] 冲突案例能正确提示

## 7. 下一阶段计划

- 下一阶段是 `S6：分类、归档计划与回滚`。
- 重点应转向虚拟归档、物理归档预览、确认执行、审计与最近一次批量回滚。
- 本阶段不会提前实现 `S6`，必须在收到明确推进指令后再进入。

## 8. 2026-04-06 查询计划与 CLI 收口修订

- `QueryPlan.intent` 不再让 `哪些 / 列出` 这类表面词直接篡权；当前实现先看 `requested_fact_keys / requested_insight_kinds`，再决定 `fact / fact_list / summary / compare / timeline` 路由。
- 新增 `fact_list` 路径，枚举型事实问题现在按“结构化事实去重后的值集合”回答，不再误落入摘要路径。
- CLI 已补齐 `opendocs qa answer|summary|insights`，`S5` 不再只存在于服务层和测试里。
- Markdown 导出 CLI 继续遵守双阶段约束：先打印 preview，再要求 `--confirmed` 才允许写文件。
