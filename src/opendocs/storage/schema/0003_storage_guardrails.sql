-- Backfill storage guardrails for databases created before 0001 constraint hardening.

CREATE TRIGGER ck_chunks_char_range_insert
BEFORE INSERT ON chunks
WHEN NEW.char_end < NEW.char_start
BEGIN
    SELECT RAISE(ABORT, 'ck_chunks_char_range');
END;

CREATE TRIGGER ck_chunks_char_range_update
BEFORE UPDATE OF char_start, char_end ON chunks
WHEN NEW.char_end < NEW.char_start
BEGIN
    SELECT RAISE(ABORT, 'ck_chunks_char_range');
END;

CREATE TRIGGER ck_memory_items_ttl_days_non_negative_insert
BEFORE INSERT ON memory_items
WHEN NEW.ttl_days IS NOT NULL AND NEW.ttl_days < 0
BEGIN
    SELECT RAISE(ABORT, 'ck_memory_items_ttl_days_non_negative');
END;

CREATE TRIGGER ck_memory_items_ttl_days_non_negative_update
BEFORE UPDATE OF ttl_days ON memory_items
WHEN NEW.ttl_days IS NOT NULL AND NEW.ttl_days < 0
BEGIN
    SELECT RAISE(ABORT, 'ck_memory_items_ttl_days_non_negative');
END;

CREATE TRIGGER ck_file_operation_plans_item_count_non_negative_insert
BEFORE INSERT ON file_operation_plans
WHEN NEW.item_count < 0
BEGIN
    SELECT RAISE(ABORT, 'ck_file_operation_plans_item_count_non_negative');
END;

CREATE TRIGGER ck_file_operation_plans_item_count_non_negative_update
BEFORE UPDATE OF item_count ON file_operation_plans
WHEN NEW.item_count < 0
BEGIN
    SELECT RAISE(ABORT, 'ck_file_operation_plans_item_count_non_negative');
END;
