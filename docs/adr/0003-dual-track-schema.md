# ADR-0003：ORM/SQL 双轨 Schema 维护策略

- 状态：Accepted
- 日期：2026-03-05
- 阶段：S1（记录 S1 设计决策）

## 背景

OpenDocs 同时维护两套 schema 定义：

1. **SQLAlchemy ORM 模型**（`src/opendocs/domain/models.py`）：用于应用层 CRUD，提供类型安全和 Python 对象映射。
2. **原始 SQL 迁移**（`src/opendocs/storage/schema/0001_initial.sql`）：用于 `sqlite3` 直接建表，保留 SQLite 特有功能（FTS5 虚拟表、触发器、`executescript` 原子迁移）。

相应地，存在两套数据库连接管理：
- `sqlite3.connect()`：用于迁移管道（`db.py` 中的 `migrate()`），因为 SQLAlchemy 的 `DDL` 抽象无法表达 FTS5 和触发器。
- `sqlalchemy.create_engine()`：用于应用层 CRUD（`build_sqlite_engine()` + `session_scope()`）。

## 决策

**接受双轨维护，用自动化测试防止漂移。**

- ORM 和 SQL 各自是 schema 的权威来源：ORM 面向应用层，SQL 面向数据库层。
- `tests/unit/storage/test_schema_consistency.py` 提供以下漂移防护：
  - `test_all_orm_tables_exist_after_migrations`：ORM 声明的表必须在迁移后存在。
  - `test_orm_columns_match_migration_columns`：逐列对比名称和 NOT NULL 属性。
  - `test_orm_indexes_match_migration_indexes`：ORM 声明的索引必须在 DB 中存在且列一致。

## 理由

1. **SQLAlchemy 无法声明 FTS5 虚拟表和触发器**：`chunk_fts` 表和 `chunks_ai/ad/au` 触发器只能通过原始 SQL 创建。
2. **`executescript` 原子迁移**：迁移管道使用 `BEGIN IMMEDIATE` + `executescript` 实现单文件原子应用，这需要 `sqlite3` 原生连接。
3. **测试防护网成本低**：一致性测试在 CI 中自动运行，增量维护成本极低。

## 时间格式约定

所有时间字段在 SQLite 中以 `TEXT` 类型存储，格式固定为 `YYYY-MM-DD HH:MM:SS`（即 SQLite `datetime('now')` 的默认输出格式）。ORM 层通过 `DateTime` 类型自动做 `datetime ↔ str` 转换。

- Raw SQL 写入（seed 脚本、迁移脚本）必须使用 `datetime('now')` 或等价的 `YYYY-MM-DD HH:MM:SS` 格式字符串。
- 禁止使用 ISO 8601 `T` 分隔符（如 `2026-03-05T10:00:00`），因为 SQLAlchemy 的 `DateTime` 反序列化依赖空格分隔。
- Python 层统一通过 `utcnow_naive()` 生成时间，该函数返回 UTC 时区无感知 datetime，`.isoformat()` 输出为 `YYYY-MM-DDTHH:MM:SS` 格式（带 `T`），但 ORM 会正确处理。直接拼接到 raw SQL 时需替换 `T` 为空格。
- **精度统一**：`utcnow_naive()` 截断微秒（`microsecond=0`），确保 ORM 写入的时间与 SQLite `datetime('now')` 的秒级精度一致。禁止绕过 `utcnow_naive()` 直接调用 `datetime.now()` 生成时间。

## 布尔字段约定

SQLite 无原生 `BOOLEAN` 类型。ORM 中使用 `Mapped[bool]` 的字段，在 SQL 中以 `INTEGER NOT NULL DEFAULT 0` 表达（0=False, 1=True）。SQLAlchemy 自动做 `bool ↔ int` 转换。Raw SQL 查询此类字段时必须使用 `0/1`，不可使用 `true/false`。

当前受影响字段：`documents.is_deleted_from_fs`。

## 已知风险

- **新增列/索引时需同步两处**：开发者必须同时修改 `models.py` 和 `0001_initial.sql`（或新迁移文件），否则 CI 会失败。
- **CHECK 约束未自动比对**：当前测试不对比 CHECK 约束文本，依赖代码审查保持一致。

## 影响

- 每次 schema 变更必须通过 `test_schema_consistency.py` 全部测试。
- 两套连接管理器的职责分明：`sqlite3` 仅用于迁移，`sqlalchemy` 仅用于 CRUD。
