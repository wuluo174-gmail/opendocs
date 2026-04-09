-- S1 storage baseline hardening:
-- 1. add task_events as the structured upstream fact table for memory
-- 2. tighten memory_items to the spec contract (no M0/session persistence)
-- 3. extend audit_logs target types with task_event/artifact

CREATE TABLE IF NOT EXISTS task_events (
    event_id TEXT PRIMARY KEY CHECK (
        length(event_id) = 36
        AND substr(event_id, 9, 1) = '-'
        AND substr(event_id, 14, 1) = '-'
        AND substr(event_id, 19, 1) = '-'
        AND substr(event_id, 24, 1) = '-'
        AND length(replace(event_id, '-', '')) = 32
        AND lower(event_id) = event_id
        AND NOT replace(event_id, '-', '') GLOB '*[^0-9a-f]*'
    ),
    trace_id TEXT NOT NULL CHECK (length(trace_id) > 0),
    stage_id TEXT NOT NULL CHECK (length(stage_id) > 0),
    task_type TEXT NOT NULL CHECK (length(task_type) > 0),
    scope_type TEXT NOT NULL CHECK (scope_type IN ('session', 'task', 'user')),
    scope_id TEXT NOT NULL CHECK (length(scope_id) > 0),
    input_summary TEXT NOT NULL,
    output_summary TEXT NOT NULL,
    related_chunk_ids_json TEXT NOT NULL DEFAULT '[]',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    related_plan_id TEXT CHECK (
        related_plan_id IS NULL
        OR (
            length(related_plan_id) = 36
            AND substr(related_plan_id, 9, 1) = '-'
            AND substr(related_plan_id, 14, 1) = '-'
            AND substr(related_plan_id, 19, 1) = '-'
            AND substr(related_plan_id, 24, 1) = '-'
            AND length(replace(related_plan_id, '-', '')) = 32
            AND lower(related_plan_id) = related_plan_id
            AND NOT replace(related_plan_id, '-', '') GLOB '*[^0-9a-f]*'
        )
    ),
    artifact_ref TEXT,
    occurred_at TEXT NOT NULL DEFAULT (datetime('now')),
    persisted_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(related_plan_id) REFERENCES file_operation_plans(plan_id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_task_events_trace ON task_events (trace_id);
CREATE INDEX IF NOT EXISTS idx_task_events_scope ON task_events (scope_type, scope_id);
CREATE INDEX IF NOT EXISTS idx_task_events_occurred_at ON task_events (occurred_at);
CREATE INDEX IF NOT EXISTS idx_task_events_related_plan ON task_events (related_plan_id);

DROP INDEX IF EXISTS idx_memory_items_active_scope_key;
DROP INDEX IF EXISTS idx_memory_items_scope;
DROP INDEX IF EXISTS idx_memory_items_supersedes_memory;

ALTER TABLE memory_items RENAME TO memory_items_legacy_0013;

CREATE TABLE memory_items (
    memory_id TEXT PRIMARY KEY CHECK (
        length(memory_id) = 36
        AND substr(memory_id, 9, 1) = '-'
        AND substr(memory_id, 14, 1) = '-'
        AND substr(memory_id, 19, 1) = '-'
        AND substr(memory_id, 24, 1) = '-'
        AND length(replace(memory_id, '-', '')) = 32
        AND lower(memory_id) = memory_id
        AND NOT replace(memory_id, '-', '') GLOB '*[^0-9a-f]*'
    ),
    memory_type TEXT NOT NULL CHECK (memory_type IN ('M1', 'M2')),
    memory_kind TEXT NOT NULL CHECK (
        memory_kind IN ('task_snapshot', 'retry_point', 'preference_pattern', 'workflow_hint')
    ),
    scope_type TEXT NOT NULL CHECK (scope_type IN ('task', 'user')),
    scope_id TEXT NOT NULL,
    key TEXT NOT NULL,
    content TEXT NOT NULL,
    source_event_ids_json TEXT NOT NULL DEFAULT '[]',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    importance REAL NOT NULL DEFAULT 0.5 CHECK (importance >= 0.0 AND importance <= 1.0),
    confidence REAL NOT NULL DEFAULT 1.0 CHECK (confidence >= 0.0 AND confidence <= 1.0),
    status TEXT NOT NULL DEFAULT 'active' CHECK (
        status IN ('active', 'expired', 'disabled', 'superseded')
    ),
    review_window_days INTEGER NOT NULL DEFAULT 30 CHECK (review_window_days >= 0),
    user_confirmed_count INTEGER NOT NULL DEFAULT 0 CHECK (user_confirmed_count >= 0),
    last_user_confirmed_at TEXT,
    recall_count INTEGER NOT NULL DEFAULT 0 CHECK (recall_count >= 0),
    last_recalled_at TEXT,
    decay_score REAL NOT NULL DEFAULT 0.0 CHECK (decay_score >= 0.0 AND decay_score <= 1.0),
    promotion_state TEXT NOT NULL DEFAULT 'promoted' CHECK (
        promotion_state IN ('candidate', 'promoted')
    ),
    consolidated_from_json TEXT NOT NULL DEFAULT '[]',
    supersedes_memory_id TEXT CHECK (
        supersedes_memory_id IS NULL
        OR (
            length(supersedes_memory_id) = 36
            AND substr(supersedes_memory_id, 9, 1) = '-'
            AND substr(supersedes_memory_id, 14, 1) = '-'
            AND substr(supersedes_memory_id, 19, 1) = '-'
            AND substr(supersedes_memory_id, 24, 1) = '-'
            AND length(replace(supersedes_memory_id, '-', '')) = 32
            AND lower(supersedes_memory_id) = supersedes_memory_id
            AND NOT replace(supersedes_memory_id, '-', '') GLOB '*[^0-9a-f]*'
        )
    ),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(supersedes_memory_id) REFERENCES memory_items(memory_id) ON DELETE SET NULL
);

DROP TABLE memory_items_legacy_0013;

CREATE UNIQUE INDEX idx_memory_items_active_scope_key
    ON memory_items (memory_type, scope_type, scope_id, key)
    WHERE status = 'active' AND promotion_state = 'promoted';
CREATE INDEX idx_memory_items_scope ON memory_items (scope_type, scope_id);
CREATE INDEX idx_memory_items_supersedes_memory ON memory_items (supersedes_memory_id);

DROP INDEX IF EXISTS idx_audit_logs_timestamp;
DROP INDEX IF EXISTS idx_audit_logs_trace_id;
DROP INDEX IF EXISTS idx_audit_logs_target;
DROP INDEX IF EXISTS idx_audit_logs_operation;

ALTER TABLE audit_logs RENAME TO audit_logs_legacy_0013;

CREATE TABLE audit_logs (
    audit_id TEXT PRIMARY KEY CHECK (
        length(audit_id) = 36
        AND substr(audit_id, 9, 1) = '-'
        AND substr(audit_id, 14, 1) = '-'
        AND substr(audit_id, 19, 1) = '-'
        AND substr(audit_id, 24, 1) = '-'
        AND length(replace(audit_id, '-', '')) = 32
        AND lower(audit_id) = audit_id
        AND NOT replace(audit_id, '-', '') GLOB '*[^0-9a-f]*'
    ),
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    actor TEXT NOT NULL CHECK (actor IN ('user', 'system', 'model')),
    operation TEXT NOT NULL,
    target_type TEXT NOT NULL CHECK (
        target_type IN (
            'document', 'plan', 'memory', 'task_event', 'answer',
            'source', 'search', 'provider_call',
            'generation', 'index_run', 'rollback', 'artifact'
        )
    ),
    target_id TEXT NOT NULL,
    result TEXT NOT NULL CHECK (result IN ('success', 'failure')),
    detail_json TEXT NOT NULL DEFAULT '{}',
    trace_id TEXT NOT NULL CHECK (length(trace_id) > 0)
);

INSERT INTO audit_logs (
    audit_id,
    timestamp,
    actor,
    operation,
    target_type,
    target_id,
    result,
    detail_json,
    trace_id
)
SELECT
    audit_id,
    timestamp,
    actor,
    operation,
    target_type,
    target_id,
    result,
    detail_json,
    trace_id
FROM audit_logs_legacy_0013;

DROP TABLE audit_logs_legacy_0013;

CREATE INDEX idx_audit_logs_timestamp ON audit_logs (timestamp);
CREATE INDEX idx_audit_logs_trace_id ON audit_logs (trace_id);
CREATE INDEX idx_audit_logs_target ON audit_logs (target_type, target_id);
CREATE INDEX idx_audit_logs_operation ON audit_logs (operation);
