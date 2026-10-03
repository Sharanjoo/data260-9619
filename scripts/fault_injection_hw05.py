"""HW5 Part 3.20: deterministic fault-injection experiment.

Runs 50 calls at each of three injected failure rates (0%, 20%, 50%) --
150 calls total -- against a real domain-tool operation
(search_recalls("a", limit=5) over your live s9619_rel database), each
wrapped in the Part 3 retry/backoff policy (mcp_servers/retry_policy.py).

Each attempt's "should this fail" decision is drawn from a
random.Random(VERIFY_SEED) instance seeded fresh at the start of each
failure-rate's 50-call batch, so re-running this script reproduces the
identical success/failure sequence (and, since the same rng also drives
backoff jitter, very close to identical timings) every time -- per the
spec's "the same seed must produce the same success/failure sequence each
time." VERIFY_SEED = 260000 + SID4 = 269619 (Section 0).

A forced failure sleeps past the per-attempt timeout instead of calling
the real database, so with_retry's own timeout enforcement is what catches
it -- a genuine timeout, not a faked exception -- while a non-forced
attempt runs the real query against your live data.

Writes:
  reports/hw05/raw/fault_injection_raw.csv      -- all 150 call-level records
  reports/hw05/raw/fault_injection_summary.json -- the 3-row results table

Also prints the filled-in METRICS.md results table to stdout.

Usage (from the repo root; MySQL must be running):
    python scripts/fault_injection_hw05.py
"""
from __future__ import annotations

import csv
import json
import random
import sys
import time
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "mcp_servers"))

from retry_policy import VERIFY_SEED, fault_wrapped, with_retry  # noqa: E402
from domain_tools import search_recalls  # noqa: E402

RAW_DIR = ROOT / "reports" / "hw05" / "raw"
TIMEOUT_S = 0.25
MAX_RETRIES = 3
CALLS_PER_RATE = 50
RATES = [0.0, 0.2, 0.5]


def run_rate(failure_rate: float) -> List[dict]:
    # Fresh rng per rate (not continued across rates) -- re-running this
    # script reproduces each rate's sequence independently and identically.
    rng = random.Random(VERIFY_SEED)
    records = []
    for i in range(CALLS_PER_RATE):
        real_op = lambda: search_recalls("a", limit=5)  # noqa: E731 -- cheap, broad-match query
        op = fault_wrapped(real_op, failure_rate, rng, timeout_s=TIMEOUT_S)
        outcome = with_retry(
            op, max_retries=MAX_RETRIES, timeout_s=TIMEOUT_S, rng=rng
        )
        records.append(
            {
                "failure_rate": failure_rate,
                "call_index": i,
                "ok": outcome.ok,
                "attempts": outcome.attempts,
                "total_latency_ms": round(outcome.total_latency_ms, 2),
                "error": outcome.error,
            }
        )
    return records


def percentile(values: List[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * p
    f, c = int(k), min(int(k) + 1, len(s) - 1)
    if f == c:
        return s[f]
    return s[f] + (s[c] - s[f]) * (k - f)


def summarize(records: List[dict], failure_rate: float) -> Dict:
    rows = [r for r in records if r["failure_rate"] == failure_rate]
    latencies = [r["total_latency_ms"] for r in rows]
    successes = sum(1 for r in rows if r["ok"])
    return {
        "injected_failure_rate": failure_rate,
        "calls": len(rows),
        "success_rate": round(successes / len(rows), 4) if rows else 0.0,
        "mean_latency_ms": round(sum(latencies) / len(latencies), 2) if latencies else 0.0,
        "p99_latency_ms": round(percentile(latencies, 0.99), 2),
    }


def main() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    all_records: List[dict] = []
    summaries = []
    for rate in RATES:
        print(f"Running {CALLS_PER_RATE} calls at injected_failure_rate="
              f"{rate:.0%} (seed={VERIFY_SEED}) ...")
        records = run_rate(rate)
        all_records.extend(records)
        summary = summarize(records, rate)
        summaries.append(summary)
        print(f"  -> success_rate={summary['success_rate']:.2%}  "
              f"mean_latency_ms={summary['mean_latency_ms']}  "
              f"p99_latency_ms={summary['p99_latency_ms']}")

    csv_path = RAW_DIR / "fault_injection_raw.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["failure_rate", "call_index", "ok", "attempts", "total_latency_ms", "error"],
        )
        writer.writeheader()
        writer.writerows(all_records)
    print(f"\nWrote {len(all_records)} raw call records -> {csv_path}")

    summary_path = RAW_DIR / "fault_injection_summary.json"
    with open(summary_path, "w") as f:
        json.dump(
            {
                "homework_number": 5,
                "sid4": 9619,
                "seed_used": VERIFY_SEED,
                "timeout_s": TIMEOUT_S,
                "max_retries": MAX_RETRIES,
                "calls_per_rate": CALLS_PER_RATE,
                "results": summaries,
            },
            f,
            indent=2,
        )
    print(f"Wrote summary -> {summary_path}")

    print("\nMETRICS.md table (paste this in):\n")
    print("| Injected failure rate | Success rate | Mean latency (ms) | p99 latency (ms) |")
    print("|---|---|---|---|")
    for s in summaries:
        print(f"| {s['injected_failure_rate']:.0%} | {s['success_rate']:.2%} | "
              f"{s['mean_latency_ms']} | {s['p99_latency_ms']} |")


if __name__ == "__main__":
    main()
