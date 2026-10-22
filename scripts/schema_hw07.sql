-- HW7 Part 1 migration for database s9619_rel: users table -> (id, username, password_hash, role).
-- scripts/migrate_hw07.py runs these steps idempotently (it skips anything already applied);
-- this file is the literal reference of what it does. code/db.py defines the same shape.
USE s9619_rel;

ALTER TABLE users ADD COLUMN username VARCHAR(80) NULL;
ALTER TABLE users ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'reader';

-- Legacy HW4 columns stay but become optional.
ALTER TABLE users MODIFY COLUMN name  VARCHAR(120) NULL;
ALTER TABLE users MODIFY COLUMN email VARCHAR(190) NULL;

-- Existing HW4 users get a unique username derived from their email, and the reader role.
UPDATE users
   SET username = CONCAT(COALESCE(NULLIF(SUBSTRING_INDEX(email, '@', 1), ''), 'user'), '_', id)
 WHERE username IS NULL;

ALTER TABLE users MODIFY COLUMN username VARCHAR(80) NOT NULL;
ALTER TABLE users ADD CONSTRAINT uq_users_username UNIQUE (username);
ALTER TABLE users ADD CONSTRAINT ck_users_role CHECK (role IN ('reader', 'writer', 'moderator'));

-- The HW4 `sessions` table is no longer used by any route. It is left in place
-- (dropping it is optional): DROP TABLE IF EXISTS sessions;
