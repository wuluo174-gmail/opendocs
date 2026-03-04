-- Backfill audit target_type constraint for legacy databases that missed CHECK.

CREATE TRIGGER ck_audit_logs_target_type_insert
BEFORE INSERT ON audit_logs
WHEN NEW.target_type NOT IN ('document', 'plan', 'memory', 'answer')
BEGIN
    SELECT RAISE(ABORT, 'ck_audit_logs_target_type');
END;

CREATE TRIGGER ck_audit_logs_target_type_update
BEFORE UPDATE OF target_type ON audit_logs
WHEN NEW.target_type NOT IN ('document', 'plan', 'memory', 'answer')
BEGIN
    SELECT RAISE(ABORT, 'ck_audit_logs_target_type');
END;
