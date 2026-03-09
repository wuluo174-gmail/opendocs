# ADR-0011: Docx 表格 heading_path 通过文档顺序遍历修复

- 状态：已接受
- 日期：2026-03-08
- 关联阶段：S2

## 上下文

python-docx 的 `doc.paragraphs` 和 `doc.tables` 是独立的集合。如果先遍历所有段落再遍历所有表格，表格的 `heading_path` 会一律继承最后一个 heading 的路径，而非表格在文档中实际位置对应的 heading。

例如："Heading 1 → Table A → Heading 2 → Table B" 中，Table A 和 Table B 都会被标注为 Heading 2 下的内容。

## 决策

改用 `doc.element.body` 的子元素迭代，按 XML 文档顺序处理 `w:p`（段落）和 `w:tbl`（表格）元素。这样每个表格在遍历到时，`heading_stack` 反映的是其前方最近的 heading，heading_path 定位准确。

## 影响

- 修复了表格 heading_path 不准的问题。
- 需要直接操作 `docx.oxml` 层的 XML 元素，但这是 python-docx 的公开 API。
- 段落文本提取改为从 `w:r/w:t` run 元素拼接，与 python-docx 内部实现一致。
