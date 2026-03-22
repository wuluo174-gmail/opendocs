-- S3: scan_runs table for persisted source scan history.

CREATE TABLE scan_runs (
    scan_run_id TEXT PRIMARY KEY CHECK (
        length(scan_run_id) = 36
        AND substr(scan_run_id, 9, 1) = '-'
        AND substr(scan_run_id, 14, 1) = '-'
        AND substr(scan_run_id, 19, 1) = '-'
        AND substr(scan_run_id, 24, 1) = '-'
        AND length(replace(scan_run_id, '-', '')) = 32
        AND lower(scan_run_id) = scan_run_id
        AND NOT replace(scan_run_id, '-', '') GLOB '*[^0-9a-f]*'
    ),
    source_root_id TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL DEFAULT 'running'
        CHECK (status IN ('running', 'completed', 'failed')),
    included_count INTEGER NOT NULL DEFAULT 0 CHECK (included_count >= 0),
    excluded_count INTEGER NOT NULL DEFAULT 0 CHECK (excluded_count >= 0),
    unsupported_count INTEGER NOT NULL DEFAULT 0 CHECK (unsupported_count >= 0),
    failed_count INTEGER NOT NULL DEFAULT 0 CHECK (failed_count >= 0),
    error_summary_json TEXT NOT NULL DEFAULT '[]',
    trace_id TEXT NOT NULL CHECK (length(trace_id) > 0),
    FOREIGN KEY(source_root_id) REFERENCES source_roots(source_root_id) ON DELETE RESTRICT
);

CREATE INDEX idx_scan_runs_source ON scan_runs (source_root_id);
CREATE INDEX idx_scan_runs_trace ON scan_runs (trace_id);
