-- HW9 Part 1 migration for database s9619_rel: a persisted view counter on the primary entity table.
-- scripts/migrate_hw09.py runs this idempotently (it skips the step when the column already exists);
-- this file is the literal reference of what it does. code/db.py defines the same column.
USE s9619_rel;

ALTER TABLE recall_record
    ADD COLUMN view_count INT NOT NULL DEFAULT 0;
