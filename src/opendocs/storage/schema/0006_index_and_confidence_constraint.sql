-- Add missing audit_logs.operation index and knowledge_items.confidence range constraint.
--
-- audit_logs.operation: AuditLogModel declares index=True but no SQL index existed,
-- causing schema divergence between the migration path (production) and
-- Base.metadata.create_all() path (ORM tests).
--
-- knowledge_items.confidence: other numeric fields (item_count, ttl_days) have range
-- guards; confidence [0.0, 1.0] was missing.  SQLite does not support
-- ALTER TABLE ADD CONSTRAINT, so triggers enforce the invariant for legacy databases.

CREATE INDEX idx_audit_logs_operation ON audit_logs (operation);

CREATE TRIGGER ck_knowledge_items_confidence_range_insert
BEFORE INSERT ON knowledge_items
WHEN NEW.confidence < 0.0 OR NEW.confidence > 1.0
BEGIN
    SELECT RAISE(ABORT, 'ck_knowledge_items_confidence_range');
END;

CREATE TRIGGER ck_knowledge_items_confidence_range_update
BEFORE UPDATE OF confidence ON knowledge_items
WHEN NEW.confidence < 0.0 OR NEW.confidence > 1.0
BEGIN
    SELECT RAISE(ABORT, 'ck_knowledge_items_confidence_range');
END;
