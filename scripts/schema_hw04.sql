-- HW4 Part 2/3 schema for database s9619_rel (PREFIX=s9619 + "_rel").
-- This is the literal migration; code/db.py's SQLAlchemy models define the
-- same schema and are what actually creates it at app startup (init_db()).
-- Kept in sync by hand -- if you change one, change the other.

CREATE DATABASE IF NOT EXISTS s9619_rel CHARACTER SET utf8mb4;
USE s9619_rel;

-- Part 2 required table: users(id, name, email UNIQUE, password_hash)
CREATE TABLE IF NOT EXISTS users (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    name          VARCHAR(120) NOT NULL,
    email         VARCHAR(190) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    UNIQUE KEY uq_users_email (email)
) ENGINE=InnoDB;

-- Part 2 required table: sessions(id [opaque token], user_id, created_at, expires_at)
CREATE TABLE IF NOT EXISTS sessions (
    id         VARCHAR(64) PRIMARY KEY,
    user_id    INT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    expires_at DATETIME NOT NULL,
    CONSTRAINT fk_sessions_user FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB;

-- Part 3's "200 related rows" -- reporting/inspection source, just test data.
CREATE TABLE IF NOT EXISTS recall_source (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    source_name   VARCHAR(150) NOT NULL,
    source_region VARCHAR(100) NOT NULL
) ENGINE=InnoDB;

-- Part 2 required primary entity table: auto-increment id, primary field,
-- secondary field -- plus the Part 3 FK to recall_source.
CREATE TABLE IF NOT EXISTS recall_record (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    product_name VARCHAR(200) NOT NULL,   -- primary field
    brand_name   VARCHAR(150) NOT NULL,   -- secondary field
    source_id    INT NULL,
    CONSTRAINT fk_recall_record_source FOREIGN KEY (source_id) REFERENCES recall_source(id)
) ENGINE=InnoDB;

-- Part 3 step 8: one index added after measuring the naive/fixed baselines.
-- NOTE: recall_record.source_id already has an implicit index because InnoDB
-- auto-creates one for any FOREIGN KEY column (required for constraint checks),
-- so indexing it again would show no real EXPLAIN difference. Instead we index
-- product_name, which speeds up a realistic "look up a recall by product name"
-- query from a full table scan to an index lookup.
-- Added by scripts/add_index_hw04.py; kept here for reference of what it runs:
CREATE INDEX idx_recall_record_product_name ON recall_record (product_name);
