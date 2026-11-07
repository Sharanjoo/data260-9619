"""HW9 Part 1: add recall_record.view_count to the live MySQL database (idempotent).

Run from the repo root with MySQL up (docker compose up -d mysql):
    python scripts/migrate_hw09.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "code"))

from cache_layer import config  # noqa: E402,F401  (sets the laptop MYSQL_HOST/PORT defaults before db is imported)
from sqlalchemy import text  # noqa: E402

from db import engine  # noqa: E402


def main() -> int:
    print(config.BANNER + " | migrate_hw09", flush=True)
    with engine.begin() as conn:
        has = conn.execute(text(
            "SELECT COUNT(*) FROM information_schema.columns "
            "WHERE table_schema = DATABASE() AND table_name = 'recall_record' AND column_name = 'view_count'")).scalar()
        if has:
            print("recall_record.view_count already exists - nothing to do")
        else:
            conn.execute(text("ALTER TABLE recall_record ADD COLUMN view_count INT NOT NULL DEFAULT 0"))
            print("added recall_record.view_count INT NOT NULL DEFAULT 0")
        rows = conn.execute(text("SELECT COUNT(*) FROM recall_record")).scalar()
        print(f"recall_record rows: {rows}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
