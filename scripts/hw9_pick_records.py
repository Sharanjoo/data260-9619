"""HW9: pick the real recall_record rows that the cache questions are about (deterministic, SEED = 9619).

    python scripts/hw9_pick_records.py          -> reports/hw09/raw/records_picked.json

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
        rows = [dict(r) for r in conn.execute(text(
            "SELECT r.id, r.record_code, r.product_name, r.brand_name, r.units_affected, "
            "       s.source_name, s.source_region, s.source_code "
            "FROM recall_record r JOIN recall_source s ON s.id = r.source_id "
            "WHERE r.units_affected > 0 ORDER BY r.id")).mappings()]
    print(f"eligible records: {len(rows)}")
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
            if need_sibling and not any(o["id"] != r["id"] and o["units_affected"] != r["units_affected"]
                                        and o["id"] not in used_ids for o in by_base[b]):
                continue
            used_bases.add(b)
            used_ids.add(r["id"])
            return r
        return None

    base = [take(need_sibling=(k < 5)) for k in range(20)]
    sibling = []
    for r in base[:5]:
        b = base_name(r["product_name"])
        options = [o for o in by_base[b] if o["id"] != r["id"] and o["units_affected"] != r["units_affected"]
                   and o["id"] not in used_ids]
        pick = options[rng.randrange(len(options))]
        used_ids.add(pick["id"])
        sibling.append(pick)
    part2 = [take(False) for _ in range(6)]
    stale = [take(False)]
    groups = {"base": base, "sibling": sibling, "part2": part2, "stale": stale}
    if any(x is None for g in groups.values() for x in g):
        print("not enough distinct products to fill every group")
        return 1

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"seed": config.SEED, "groups": groups}, indent=2, ensure_ascii=False), encoding="utf-8")
    for name, g in groups.items():
        print(f"\n{name} ({len(g)})")
        for r in g:
            print(f"  {r['record_code']}  units={r['units_affected']:>6}  {r['product_name']} / {r['brand_name']}  "
                  f"[{r['source_name']}, {r['source_region']}]")
    print(f"\nwritten: {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
