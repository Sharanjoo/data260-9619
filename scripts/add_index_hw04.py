"""HW4 Part 3 step 8: add one index and capture EXPLAIN output before and after.

recall_record.source_id already has an implicit index because InnoDB
auto-creates one for any FOREIGN KEY column (needed for constraint checks),
so indexing it again wouldn't show a real before/after difference. Instead
this adds an index on recall_record.product_name and demonstrates the
before/after EXPLAIN for a point lookup by product name -- a realistic
query pattern for this domain (searching recalls by product) that goes from
a full table scan to an index lookup.

Usage:
    python scripts/add_index_hw04.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "code"))

from sqlalchemy import text  # noqa: E402
from db import engine  # noqa: E402

RAW_DIR = Path(__file__).resolve().parent.parent / "reports" / "hw04" / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

INDEX_NAME = "idx_recall_record_product_name"


def ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def explain_rows(conn, sample_value: str) -> list[dict]:
    result = conn.execute(
        text("EXPLAIN SELECT id, product_name, brand_name, source_id FROM recall_record WHERE product_name = :v"),
        {"v": sample_value},
    )
    return [dict(row._mapping) for row in result]


def index_exists(conn) -> bool:
    result = conn.execute(
        text(
            "SELECT COUNT(*) FROM information_schema.statistics "
            "WHERE table_schema = DATABASE() AND table_name = 'recall_record' AND index_name = :idx"
        ),
        {"idx": INDEX_NAME},
    )
    return result.scalar() > 0


def main() -> None:
    with engine.connect() as conn:
        sample = conn.execute(
            text("SELECT product_name FROM recall_record ORDER BY id LIMIT 1 OFFSET 2500")
        ).scalar()
        if sample is None:
            print("[add_index_hw04] recall_record is empty -- run scripts/seed_hw04.py first. Aborting.")
            return
        print(f"[add_index_hw04] {ts()} sample lookup value: {sample!r}")

        already_present = index_exists(conn)
        if already_present:
            print(f"[add_index_hw04] {INDEX_NAME} already exists -- dropping it first so before/after is meaningful.")
            conn.execute(text(f"DROP INDEX {INDEX_NAME} ON recall_record"))
            conn.commit()

        print(f"[add_index_hw04] {ts()} EXPLAIN before adding index:")
        before = explain_rows(conn, sample)
        for row in before:
            print(f"  {row}")

        print(f"[add_index_hw04] {ts()} adding index: CREATE INDEX {INDEX_NAME} ON recall_record (product_name)")
        conn.execute(text(f"CREATE INDEX {INDEX_NAME} ON recall_record (product_name)"))
        conn.commit()

        print(f"[add_index_hw04] {ts()} EXPLAIN after adding index:")
        after = explain_rows(conn, sample)
        for row in after:
            print(f"  {row}")

        out = {
            "generated_at": ts(),
            "index_name": INDEX_NAME,
            "ddl": f"CREATE INDEX {INDEX_NAME} ON recall_record (product_name)",
            "sample_lookup_value": sample,
            "explain_before": before,
            "explain_after": after,
        }
        out_path = RAW_DIR / "explain_before_after.json"
        out_path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
        print(f"[add_index_hw04] {ts()} wrote {out_path}")

        before_type = before[0].get("type") if before else "?"
        before_rows = before[0].get("rows") if before else "?"
        after_type = after[0].get("type") if after else "?"
        after_rows = after[0].get("rows") if after else "?"
        print(
            f"\n[add_index_hw04] Summary: type {before_type} (~{before_rows} rows scanned) "
            f"-> type {after_type} (~{after_rows} rows scanned) after adding the index."
        )


if __name__ == "__main__":
    main()
