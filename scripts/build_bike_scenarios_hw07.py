"""HW7 Part 4: build the two Bay Wheels scenario CSVs from one real month of trips (October 2024).

  python scripts/build_bike_scenarios_hw07.py [--month 202410]

  Scenario M (membership wins): 540 real trips by Bay Wheels *members* that started in October 2024 (real
      timestamps, one calendar month; a heavy-user profile).
  Scenario P (pay-per-use wins): 504 real short (<= 15 min) classic-bike trips by *casual* riders, with SYNTHETIC
      start dates: exactly 7 trips in each of the 72 months 2019-01 .. 2024-12 (an occasional rider). Time of day
      and ride duration are the real values; the date is replaced and the original timestamp is kept in
      `orig_started_at`. The files say so; the report must say so too.
Sampling uses random.Random(9619) (the course SEED), so the files are reproducible from the same month file.
Outputs: data/bike/scenario_M_membership.csv, data/bike/scenario_P_payperuse.csv, data/bike/scenarios.json
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import random
import sys
import zipfile
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from src.bike_pricing import evaluate_trips, trip_minutes  # noqa: E402

SEED = 9619
OUT = REPO / "data" / "bike"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", default="202410")
    args = ap.parse_args()
    zpath = REPO / "data" / "baywheels_raw" / f"{args.month}-baywheels-tripdata.csv.zip"
    with zipfile.ZipFile(zpath) as zf:
        member = [m for m in zf.namelist() if m.lower().endswith(".csv") and not m.startswith("__MACOSX")][0]
        with zf.open(member) as fh:
            reader = csv.DictReader(io.TextIOWrapper(fh, encoding="utf-8", newline=""))
            fields = list(reader.fieldnames or [])
            rows = list(reader)
    print(f"read {len(rows)} trips from {zpath.name}")
    month_prefix = f"{args.month[:4]}-{args.month[4:]}"
    rng = random.Random(SEED)

    # Scenario M
    pool_m = [r for r in rows if r["member_casual"] == "member" and r["started_at"].startswith(month_prefix)]
    m_rows = sorted(rng.sample(pool_m, 540), key=lambda r: r["started_at"])

    # Scenario P
    pool_p = [r for r in rows if r["member_casual"] == "casual" and r["rideable_type"] == "classic_bike"
              and 0.5 <= trip_minutes(r) <= 15.0]
    p_pick = rng.sample(pool_p, 504)
    months = [(y, mth) for y in range(2019, 2025) for mth in range(1, 13)]
    p_rows = []
    for idx, r in enumerate(p_pick):
        y, mth = months[idx // 7]
        day = rng.randint(1, 28)
        old_start = datetime.fromisoformat(r["started_at"][:23])
        old_end = datetime.fromisoformat(r["ended_at"][:23])
        new_start = datetime(y, mth, day, old_start.hour, old_start.minute, old_start.second)
        new_end = new_start + (old_end - old_start)
        p_rows.append({**r, "started_at": new_start.strftime("%Y-%m-%d %H:%M:%S"),
                       "ended_at": new_end.strftime("%Y-%m-%d %H:%M:%S"), "orig_started_at": r["started_at"]})
    p_rows.sort(key=lambda r: r["started_at"])

    OUT.mkdir(parents=True, exist_ok=True)
    files = {"M": (OUT / "scenario_M_membership.csv", m_rows, fields),
             "P": (OUT / "scenario_P_payperuse.csv", p_rows, fields + ["orig_started_at"])}
    meta = {"seed": SEED, "source_file": zpath.name, "source_url": f"https://s3.amazonaws.com/baywheels-data/{zpath.name}",
            "source_rows": len(rows), "scenarios": {}}
    for key, (path, data, cols) in files.items():
        with path.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            w.writerows(data)
        ref = evaluate_trips(path)
        meta["scenarios"][key] = {"file": str(path.relative_to(REPO)).replace("\\", "/"), "rows": len(data),
                                  "sha256": sha256(path), "reference": {k: v for k, v in ref.items() if k != "weekly"},
                                  "weekly_rows": len(ref["weekly"])}
        print(f"\nScenario {key}: {path.name}  rows={len(data)}  sha256={meta['scenarios'][key]['sha256'][:16]}...")
        print(f"  months={ref['months']} rides/month={ref['rides_per_month']:.1f} avg minutes={ref['avg_minutes']:.1f} "
              f"bike types={ref['bike_types']}")
        print(f"  reference: pay-per-use ${ref['pay_per_use_total']:.2f} | membership ${ref['membership_total']:.2f} "
              f"(pass ${ref['membership_pass_cost']:.2f} + residual ${ref['membership_residual']:.2f}) -> {ref['decision']} "
              f"by ${ref['difference']:.2f}; break-even {ref['break_even_rides_per_month']} rides/month")
    (OUT / "scenarios.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"\nwrote {OUT / 'scenarios.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
