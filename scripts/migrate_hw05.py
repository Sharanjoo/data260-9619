"""HW5 Part 1.I: migrate the HW4 schema to the required HW5 shape.

Adds, to the existing recall_source / recall_record tables (does NOT touch
their already-correct HW4 columns or any existing row data otherwise):

recall_source (the related/"author" entity):
  - source_code  VARCHAR(40) UNIQUE NOT NULL   (new required unique field)
  - created_at   DATETIME NOT NULL
  - updated_at   DATETIME NOT NULL

recall_record (the primary entity):
  - record_code     VARCHAR(40) UNIQUE NOT NULL  (new required unique field)
  - units_affected  INT NOT NULL DEFAULT 0        (new numeric field, sensible default)
  - created_at      DATETIME NOT NULL
  - updated_at      DATETIME NOT NULL

Existing rows (200 recall_source / 5000+ recall_record from HW4's seed step,
plus anything created later through the API) get deterministic backfilled
values for the new NOT NULL columns before the NOT NULL/UNIQUE constraints
are applied, so this is safe to run against live HW4 data without deleting
or resetting anything.

Idempotent: safe to run multiple times. Only adds what's missing.

Usage:
    python scripts/migrate_hw05.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "code"))

from sqlalchemy import text  # noqa: E402
from db import engine  # noqa: E402


def column_exists(conn, table: str, column: str) -> bool:
    result = conn.execute(
        text(
            "SELECT COUNT(*) FROM information_schema.columns "
            "WHERE table_schema = DATABASE() AND table_name = :t AND column_name = :c"
        ),
        {"t": table, "c": column},
    )
    return result.scalar() > 0


def add_column_if_missing(conn, table: str, column: str, ddl: str) -> None:
    if column_exists(conn, table, column):
        print(f"[migrate_hw05]   {table}.{column} already exists -- skipping ADD COLUMN")
        return
    print(f"[migrate_hw05]   ALTER TABLE {table} ADD COLUMN {ddl}")
    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {ddl}"))
    conn.commit()


def _finalize_column(conn, table: str, column: str, new_type_and_null: str) -> None:
    print(f"[migrate_hw05]   ALTER TABLE {table} MODIFY COLUMN {column} {new_type_and_null}")
    conn.execute(text(f"ALTER TABLE {table} MODIFY COLUMN {column} {new_type_and_null}"))
    conn.commit()


def _index_exists(conn, table: str, index_name: str) -> bool:
    result = conn.execute(
        text(
            "SELECT COUNT(*) FROM information_schema.statistics "
            "WHERE table_schema = DATABASE() AND table_name = :t AND index_name = :i"
        ),
        {"t": table, "i": index_name},
    )
    return result.scalar() > 0


def _add_unique_index_if_missing(conn, table: str, column: str, index_name: str) -> None:
    if _index_exists(conn, table, index_name):
        print(f"[migrate_hw05]   {index_name} already exists -- skipping")
        return
    print(f"[migrate_hw05]   CREATE UNIQUE INDEX {index_name} ON {table} ({column})")
    conn.execute(text(f"CREATE UNIQUE INDEX {index_name} ON {table} ({column})"))
    conn.commit()


def migrate_recall_source(conn) -> None:
    print("[migrate_hw05] recall_source ...")
    add_column_if_missing(conn, "recall_source", "source_code", "source_code VARCHAR(40) NULL")
    add_column_if_missing(conn, "recall_source", "created_at", "created_at DATETIME NULL")
    add_column_if_missing(conn, "recall_source", "updated_at", "updated_at DATETIME NULL")

    missing = conn.execute(text("SELECT id FROM recall_source WHERE source_code IS NULL")).scalars().all()
    for row_id in missing:
        conn.execute(
            text("UPDATE recall_source SET source_code = :code WHERE id = :id"),
            {"code": f"SRC-{row_id:05d}", "id": row_id},
        )
    conn.execute(text("UPDATE recall_source SET created_at = NOW() WHERE created_at IS NULL"))
    conn.execute(text("UPDATE recall_source SET updated_at = NOW() WHERE updated_at IS NULL"))
    conn.commit()
    print(f"[migrate_hw05]   backfilled source_code/timestamps for {len(missing)} existing row(s)")

    _finalize_column(conn, "recall_source", "source_code", "VARCHAR(40) NOT NULL")
    _finalize_column(conn, "recall_source", "created_at", "DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP")
    _finalize_column(conn, "recall_source", "updated_at", "DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP")
    _add_unique_index_if_missing(conn, "recall_source", "source_code", "uq_recall_source_code")


def migrate_recall_record(conn) -> None:
    print("[migrate_hw05] recall_record ...")
    add_column_if_missing(conn, "recall_record", "record_code", "record_code VARCHAR(40) NULL")
    add_column_if_missing(conn, "recall_record", "units_affected", "units_affected INT NOT NULL DEFAULT 0")
    add_column_if_missing(conn, "recall_record", "created_at", "created_at DATETIME NULL")
    add_column_if_missing(conn, "recall_record", "updated_at", "updated_at DATETIME NULL")

    missing = conn.execute(text("SELECT id FROM recall_record WHERE record_code IS NULL")).scalars().all()
    for row_id in missing:
        conn.execute(
            text("UPDATE recall_record SET record_code = :code WHERE id = :id"),
            {"code": f"REC-{row_id:06d}", "id": row_id},
        )
    conn.execute(text("UPDATE recall_record SET created_at = NOW() WHERE created_at IS NULL"))
    conn.execute(text("UPDATE recall_record SET updated_at = NOW() WHERE updated_at IS NULL"))
    conn.commit()
    print(f"[migrate_hw05]   backfilled record_code/timestamps for {len(missing)} existing row(s)")

    _finalize_column(conn, "recall_record", "record_code", "VARCHAR(40) NOT NULL")
    _finalize_column(conn, "recall_record", "created_at", "DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP")
    _finalize_column(conn, "recall_record", "updated_at", "DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP")
    _add_unique_index_if_missing(conn, "recall_record", "record_code", "uq_recall_record_code")


def main() -> None:
    with engine.connect() as conn:
        migrate_recall_source(conn)
        migrate_recall_record(conn)
    print("\n[migrate_hw05] Done. recall_source and recall_record now match the HW5 Part 1.I schema.")


if __name__ == "__main__":
    main()
