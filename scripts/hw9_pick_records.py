"""HW9: pick the real recall_record rows that the cache questions are about (deterministic, SEED = 9619).

    python scripts/hw9_pick_records.py          -> reports/hw09/raw/records_picked.json
    python scripts/hw9_seed_units.py            -> writes the planned units_affected into those rows

Every seeded recall_record has units_affected = 0 (the column was added by the HW5 migration with a default of 0), so a
question like "how many units were affected" would have no answer. This script plans a number for each picked record
(random.Random(SEED + 1), distinct values 120..48000) and stores it in the JSON as units_affected; hw9_seed_units.py
then applies it to the database. The database is only read here.

Groups (every record has a different product, so two questions about different records never share an answer):
  base      20 records whose questions are cached in Part 3
  sibling    5 more lots of the same product as base[0..4] (a nearly identical question with a different answer)
  part2      6 records for the Part 2 demonstration queries
  stale      1 record that Part 3.5 updates to make a cached answer stale
Only reads the database."""
from __future__ import annotations

import json
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "code"))

from cache_layer import config  # noqa: E402  (laptop MYSQL_HOST/PORT defaults, before db is imported)
from sqlalchemy import text  # noqa: E402

from db import engine  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "reports" / "hw09" / "raw" / "records_picked.json"
LOT = re.compile(r"\s*\(Lot \d+\)\s*$")


def base_name(product: str) -> str:
    return LOT.sub("", product).strip()


def main() -> int:
    print(config.BANNER + " | hw9_pick_records", flush=True)
    with engine.connect() as conn:
        stats = conn.execute(text(
            "SELECT COUNT(*) AS total, SUM(source_id IS NOT NULL) AS with_source, SUM(units_affected > 0) AS with_units, "
            "COUNT(DISTINCT units_affected) AS distinct_units, MIN(units_affected) AS min_units, "
            "MAX(units_affected) AS max_units FROM recall_record")).mappings().first()
        sources = conn.execute(text("SELECT COUNT(*) FROM recall_source")).scalar()
        print(f"recall_record: {dict(stats)}   recall_source rows: {sources}")
        for r in conn.execute(text("SELECT id, record_code, product_name, brand_name, units_affected, source_id "
                                   "FROM recall_record ORDER BY id LIMIT 3")).mappings():
            print("  sample:", dict(r))
        rows = [dict(r) for r in conn.execute(text(
            "SELECT r.id, r.record_code, r.product_name, r.brand_name, r.units_affected, "
            "       s.source_name, s.source_region, s.source_code "
            "FROM recall_record r JOIN recall_source s ON s.id = r.source_id "
            "ORDER BY r.id")).mappings()]
    print(f"eligible records (with a source): {len(rows)}")
    if len(rows) < 100:
        print("too few eligible records to pick from - see the counts above")
        return 1
    rng = random.Random(config.SEED)
    order = list(range(len(rows)))
    rng.shuffle(order)

    by_base: dict[str, list[dict]] = {}
    for r in rows:
        by_base.setdefault(base_name(r["product_name"]), []).append(r)

    used_bases: set[str] = set()
    used_ids: set[int] = set()

    def take(need_sibling: bool) -> dict | None:
        for i in order:
            r = rows[i]
            b = base_name(r["product_name"])
            if r["id"] in used_ids or b in used_bases:
                continue
            if need_sibling and not any(o["id"] != r["id"] and o["id"] not in used_ids for o in by_base[b]):
                continue
            used_bases.add(b)
            used_ids.add(r["id"])
            return r
        return None

    base = [take(need_sibling=(k < 5)) for k in range(20)]
    sibling = []
    for r in base[:5]:
        b = base_name(r["product_name"])
        options = [o for o in by_base[b] if o["id"] != r["id"] and o["id"] not in used_ids]
        pick = options[rng.randrange(len(options))]
        used_ids.add(pick["id"])
        sibling.append(pick)
    part2 = [take(False) for _ in range(6)]
    stale = [take(False)]
    groups = {"base": base, "sibling": sibling, "part2": part2, "stale": stale}
    if any(x is None for g in groups.values() for x in g):
        print("not enough distinct products to fill every group")
        return 1

    units_rng = random.Random(config.SEED + 1)
    values = units_rng.sample(range(120, 48001), 32)
    for r, v in zip((x for g in groups.values() for x in g), values):
        r["units_before"] = r["units_affected"]
        r["units_affected"] = v

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"seed": config.SEED, "groups": groups}, indent=2, ensure_ascii=False), encoding="utf-8")
    for name, g in groups.items():
        print(f"\n{name} ({len(g)})")
        for r in g:
            print(f"  {r['record_code']}  units {r['units_before']} -> {r['units_affected']:>6}  {r['product_name']} / {r['brand_name']}  "
                  f"[{r['source_name']}, {r['source_region']}]")
    print(f"\nwritten: {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
