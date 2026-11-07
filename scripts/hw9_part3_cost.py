"""HW9 Part 3.4: price every threshold of the sweep and choose the one to ship.

    python scripts/hw9_part3_cost.py [--rate-per-hour 1.00] [--c-false 5.00]

Reads reports/hw09/raw/part3_sweep_cases.csv and part3_agent_pass.jsonl; writes raw/part3_cost.json.

Cost model (assumptions are stated, the rest is measured):
  c_miss  = mean agent latency measured in the agent pass (seconds) x server price per second
            -> a miss keeps the model busy for that long; the price per hour is an ASSUMPTION (default $1.00/h,
               the rental price of one modest GPU/CPU inference server).
  c_false = cost of one false hit = a shopper is given another recall's number or agency, notices (or is harmed) and
            a person has to correct it. ASSUMPTION: one support contact, about 10 minutes of staff time at $30/hour = $5.00.
  total   = (cases not served from cache) x c_miss + (false hits) x c_false
A false miss therefore costs one c_miss (the agents ran needlessly); a false hit costs c_false and saves the c_miss."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "code"))

from cache_layer.config import BANNER  # noqa: E402

RAW = Path(__file__).resolve().parent.parent / "reports" / "hw09" / "raw"


def table(rows_by_thr: dict, c_miss: float, c_false: float) -> dict:
    out = {}
    for thr, rows in rows_by_thr.items():
        not_served = sum(1 for r in rows if r["served"] != "True")
        false_hits = sum(1 for r in rows if r["false_hit"] == "True")
        out[thr] = {"not_served": not_served, "false_hits": false_hits,
                    "miss_cost": round(not_served * c_miss, 4), "false_hit_cost": round(false_hits * c_false, 4),
                    "total_cost": round(not_served * c_miss + false_hits * c_false, 4)}
    return out


def best(costs: dict) -> str:
    # lowest total; on a tie the higher threshold (the safer one)
    return min(costs, key=lambda t: (costs[t]["total_cost"], -float(t)))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rate-per-hour", type=float, default=1.00)
    parser.add_argument("--c-false", type=float, default=5.00)
    args = parser.parse_args()
    print(BANNER + " | hw9_part3_cost", flush=True)

    lat = [json.loads(x)["agent_latency_ms"] for x in (RAW / "part3_agent_pass.jsonl").read_text(encoding="utf-8").splitlines()
           if x.strip() and json.loads(x)["status"] == "approved"]
    mean_s = sum(lat) / len(lat) / 1000
    c_miss = round(mean_s * args.rate_per_hour / 3600, 4)
    print(f"mean agent latency over {len(lat)} approved questions: {mean_s:.1f} s")
    print(f"c_miss  = {mean_s:.1f} s x ${args.rate_per_hour:.2f}/h / 3600 = ${c_miss:.4f}")
    print(f"c_false = ${args.c_false:.2f}   (ratio c_false / c_miss = {args.c_false / c_miss:.0f})\n")

    rows_by_thr: dict = {}
    with (RAW / "part3_sweep_cases.csv").open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            rows_by_thr.setdefault(r["threshold"], []).append(r)
    costs = table(rows_by_thr, c_miss, args.c_false)
    sweep = json.loads((RAW / "part3_sweep.json").read_text(encoding="utf-8"))["summaries"]
    print(f"{'threshold':>9} {'not served':>11} {'false hits':>11} {'miss cost':>10} {'false-hit cost':>15} {'total':>9}")
    for thr, c in costs.items():
        print(f"{float(thr):>9.2f} {c['not_served']:>11} {c['false_hits']:>11} ${c['miss_cost']:>8.2f} ${c['false_hit_cost']:>13.2f} ${c['total_cost']:>7.2f}")
    chosen = best(costs)
    print(f"\nlowest total cost: threshold {float(chosen):.2f}  (${costs[chosen]['total_cost']:.2f})")

    print("\nsensitivity: which threshold is cheapest if c_false changes (c_miss fixed)")
    sens = {}
    for cf in (0.05, 0.50, 5.00, 50.00):
        alt = table(rows_by_thr, c_miss, cf)
        sens[str(cf)] = {"best": best(alt), "totals": {t: v["total_cost"] for t, v in alt.items()}}
        print(f"  c_false ${cf:>5.2f}: cheapest threshold {float(best(alt)):.2f}   totals "
              + "  ".join(f"{float(t):.2f}=${v['total_cost']:.2f}" for t, v in alt.items()))
    (RAW / "part3_cost.json").write_text(json.dumps({
        "mean_agent_latency_s": round(mean_s, 2), "rate_per_hour": args.rate_per_hour, "c_miss": c_miss,
        "c_false": args.c_false, "costs": costs, "chosen_by_lowest_total": chosen, "sensitivity": sens,
        "sweep": sweep}, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
