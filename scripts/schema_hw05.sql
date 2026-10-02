-- HW5 Part 1.I schema migration for database s9619_rel (PREFIX=s9619 + "_rel").
-- This is the literal migration; scripts/migrate_hw05.py is what actually runs
-- it against the live database (idempotently, with backfill for existing rows).
-- Kept in sync by hand with code/db.py's SQLAlchemy models -- if you change
-- one, change the other.

USE s9619_rel;

-- Related entity ("author"-equivalent): add the required unique field + timestamps.
ALTER TABLE recall_source
    ADD COLUMN source_code VARCHAR(40) NOT NULL,
    ADD COLUMN created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ADD COLUMN updated_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    ADD UNIQUE KEY uq_recall_source_code (source_code);

-- Primary entity: add the required unique field, numeric field w/ default, timestamps.
ALTER TABLE recall_record
    ADD COLUMN record_code    VARCHAR(40) NOT NULL,
    ADD COLUMN units_affected INT NOT NULL DEFAULT 0,
    ADD COLUMN created_at     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ADD COLUMN updated_at     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    ADD UNIQUE KEY uq_recall_record_code (record_code);

-- NOTE: this literal form (plain ADD COLUMN ... NOT NULL with no prior
-- backfill) only works cleanly on an EMPTY table. Since HW4 already seeded
-- 200 recall_source / 5000+ recall_record rows, the actual migration that
-- runs against this live database is scripts/migrate_hw05.py, which adds
-- each column as nullable first, backfills deterministic source_code /
-- record_code values (SRC-00001, REC-000001, ...) and NOW() timestamps for
-- existing rows, THEN tightens to NOT NULL + UNIQUE. This file documents the
-- target end-state schema, not the exact statement sequence that was run
-- against the already-seeded database.

-- Delete-protection note (Part 1.I requirement: "prevent deletion of a
-- related-entity record that still has associated primary-entity records"):
-- recall_record.source_id's FOREIGN KEY has no ON DELETE clause, so InnoDB's
-- default behavior already rejects (RESTRICT) a DELETE on recall_source while
-- dependent recall_record rows exist. db_routes.py's delete-source endpoint
-- (Part 1.II) additionally checks this explicitly first and returns a clean
-- 409 Conflict instead of letting a raw database IntegrityError surface.
