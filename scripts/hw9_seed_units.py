"""HW9: write the planned units_affected values (from hw9_pick_records.py) into the 32 picked recall_record rows.

    python scripts/hw9_seed_units.py

Only rows that still have units_affected = 0 are changed, so running it again never overwrites a later update (the
stale-answer demo of Part 3.5 changes one of these values on purpose)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "code"))

from cache_layer import config  # noqa: E402  (laptop MYSQL_HOST/PORT defaults, before db is imported)
from sqlalchemy import text  # noqa: E402

from db import engine  # noqa: E402

PICKED = Path(__file__).resolve().parent.parent / "reports" / "hw09" / "raw" / "records_picked.json"


def main() -> int:
    print(config.BANNER + " | hw9_seed_units", flush=True)
    groups = json.loads(PICKED.read_text(encoding="utf-8"))["groups"]
    changed = kept = 0
    with engine.begin() as conn:
        for name, recs in groups.items():
            for r in recs:
                n = conn.execute(text("UPDATE recall_record SET units_affected = :u WHERE id = :i AND units_affected = 0"),
                                 {"u": r["units_affected"], "i": r["id"]}).rowcount
                changed += n
                kept += 1 - n
        total = sum(len(v) for v in groups.values())
        now = conn.execute(text("SELECT COUNT(*) FROM recall_record WHERE units_affected > 0")).scalar()
    print(f"picked records: {total}   set now: {changed}   already had a value: {kept}")
    print(f"recall_record rows with units_affected > 0: {now}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
