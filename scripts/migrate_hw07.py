"""HW7 Part 1: migrate the HW4 `users` table to the HW7 shape.

Adds `username` (UNIQUE, NOT NULL) and `role` (reader|writer|moderator,
default reader), and makes the legacy `name` / `email` columns optional.
Existing HW4 users are kept: they get a username derived from their email
and the reader role. Idempotent -- safe to run repeatedly. See
scripts/schema_hw07.sql for the literal statements.

Usage (from the repo root, with MySQL reachable like for the other scripts):
    python scripts/migrate_hw07.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Host-side script: use the host-mapped MySQL port from compose.yaml (43306), like verify_hw05.py.
os.environ.setdefault("MYSQL_PORT", "43306")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "code"))

from sqlalchemy import text  # noqa: E402

from db import engine  # noqa: E402

TAG = "[migrate_hw07]"


def column_exists(conn, table: str, column: str) -> bool:
    return conn.execute(
        text(
            "SELECT COUNT(*) FROM information_schema.columns "
            "WHERE table_schema = DATABASE() AND table_name = :t AND column_name = :c"
        ),
        {"t": table, "c": column},
    ).scalar() > 0


def unique_index_on(conn, table: str, column: str) -> bool:
    return conn.execute(
        text(
            "SELECT COUNT(*) FROM information_schema.statistics "
            "WHERE table_schema = DATABASE() AND table_name = :t "
            "AND column_name = :c AND non_unique = 0 AND seq_in_index = 1"
        ),
        {"t": table, "c": column},
    ).scalar() > 0


def check_exists(conn, table: str, name: str) -> bool:
    return conn.execute(
        text(
            "SELECT COUNT(*) FROM information_schema.table_constraints "
            "WHERE table_schema = DATABASE() AND table_name = :t "
            "AND constraint_name = :n AND constraint_type = 'CHECK'"
        ),
        {"t": table, "n": name},
    ).scalar() > 0


def run(conn, label: str, sql: str) -> None:
    print(f"{TAG}   {label}")
    conn.execute(text(sql))
    conn.commit()


def main() -> None:
    with engine.connect() as conn:
        print(f"{TAG} users ...")
        if not column_exists(conn, "users", "username"):
            run(conn, "ADD COLUMN username", "ALTER TABLE users ADD COLUMN username VARCHAR(80) NULL")
        if not column_exists(conn, "users", "role"):
            run(conn, "ADD COLUMN role",
                "ALTER TABLE users ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'reader'")
        run(conn, "make legacy name optional", "ALTER TABLE users MODIFY COLUMN name VARCHAR(120) NULL")
        run(conn, "make legacy email optional", "ALTER TABLE users MODIFY COLUMN email VARCHAR(190) NULL")

        result = conn.execute(text(
            "UPDATE users SET username = CONCAT("
            "COALESCE(NULLIF(SUBSTRING_INDEX(email, '@', 1), ''), 'user'), '_', id) "
            "WHERE username IS NULL"
        ))
        conn.commit()
        print(f"{TAG}   backfilled username for {result.rowcount} legacy row(s)")

        run(conn, "username NOT NULL", "ALTER TABLE users MODIFY COLUMN username VARCHAR(80) NOT NULL")
        if not unique_index_on(conn, "users", "username"):
            run(conn, "UNIQUE(username)", "ALTER TABLE users ADD CONSTRAINT uq_users_username UNIQUE (username)")
        if not check_exists(conn, "users", "ck_users_role"):
            run(conn, "CHECK(role)",
                "ALTER TABLE users ADD CONSTRAINT ck_users_role "
                "CHECK (role IN ('reader', 'writer', 'moderator'))")
    print(f"\n{TAG} Done. users now has id, username (unique), password_hash, role.")


if __name__ == "__main__":
    main()
