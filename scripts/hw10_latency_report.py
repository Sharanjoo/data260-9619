"""HW10 Part 4.3: p50 / p95 stage latency of the confirmed cache misses, from the spans (no model, no Kafka needed).

    python scripts/hw10_latency_report.py            -> prints the table, writes reports/hw10/raw/latency_table.json,
                                                        latency_table.csv and latency_per_request.csv (raw, one row per request)

Per confirmed miss (trace_id from data/hw10/latency_runs.jsonl) the spans give: cache_lookup, planner, writer, reviewer (the model
time of each stage, retries summed), queue wait (sum of the four queue_wait_* hops: inbox, tasks, drafts, final), request =
end-to-end latency as the client saw it, and evaluator (the judge, after the request, outside the request path). 'other' is what
is left of the end-to-end time (facts lookup, Kafka producer calls, cache store, Python overhead).
Percentiles use linear interpolation between ranks (the same as numpy's default). Share of end-to-end = mean stage time / mean
end-to-end time of the same requests (also shown: median stage / median end-to-end). Cache-hit latency is reported separately."""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "code"))

from tracing.spans import DEFAULT_PATH, read_spans  # noqa: E402

RUNS = REPO / "data" / "hw10" / "latency_runs.jsonl"
OUT = REPO / "reports" / "hw10" / "raw"
BANNER = "Sharan Lourduraj | SID4 9619 | DATA 260 HW10 Part 4.3 (latency report)"
STAGES = [("Cache lookup", "cache_lookup_ms"), ("Planner", "planner_ms"), ("Writer", "writer_ms"), ("Reviewer", "reviewer_ms"),
          ("Queue wait (total)", "queue_wait_ms"), ("Other (facts, Kafka send, cache store)", "other_ms")]


def percentile(values: List[float], q: float) -> float:
    xs = sorted(values)
    if not xs:
        raise ValueError("no values")
    pos = (len(xs) - 1) * q / 100.0
    lo = int(pos)
    hi = min(lo + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


def mean(xs: List[float]) -> float:
    return sum(xs) / len(xs)


def per_request(trace_id: str, spans: List[dict]) -> Optional[Dict[str, float]]:
    """Durations (ms) for one request, or None when a required span is missing."""
    def total(stage: str) -> Optional[float]:
        d = [s["duration_ms"] for s in spans if s["stage"] == stage]
        return sum(d) if d else None

    req, look = total("request"), total("cache_lookup")
    parts = {k: total(k) for k in ("planner", "writer", "reviewer")}
    waits = [s["duration_ms"] for s in spans if s["stage"].startswith("queue_wait_")]
    if req is None or look is None or any(v is None for v in parts.values()) or len(waits) < 4:
        return None
    row = {"trace_id": trace_id, "cache_lookup_ms": look, "planner_ms": parts["planner"], "writer_ms": parts["writer"],
           "reviewer_ms": parts["reviewer"], "queue_wait_ms": sum(waits), "end_to_end_ms": req}
    row["other_ms"] = req - (look + parts["planner"] + parts["writer"] + parts["reviewer"] + sum(waits))
    row["evaluation_ms"] = total("evaluator")
    return row


def summarize(rows: List[Dict[str, float]]) -> List[dict]:
    e2e = [r["end_to_end_ms"] for r in rows]
    out = []
    items = [(name, key) for name, key in STAGES]
    ev = [r["evaluation_ms"] for r in rows if r["evaluation_ms"] is not None]
    for name, key in items:
        xs = [r[key] for r in rows]
        out.append({"stage": name, "n": len(xs), "p50_ms": percentile(xs, 50), "p95_ms": percentile(xs, 95), "mean_ms": mean(xs),
                    "share_mean_pct": 100 * mean(xs) / mean(e2e), "share_p50_pct": 100 * percentile(xs, 50) / percentile(e2e, 50)})
    if ev:
        out.append({"stage": "Evaluation (judge, outside the request path)", "n": len(ev), "p50_ms": percentile(ev, 50),
                    "p95_ms": percentile(ev, 95), "mean_ms": mean(ev), "share_mean_pct": 100 * mean(ev) / mean(e2e),
                    "share_p50_pct": 100 * percentile(ev, 50) / percentile(e2e, 50)})
    out.append({"stage": "End-to-end (cache miss)", "n": len(e2e), "p50_ms": percentile(e2e, 50), "p95_ms": percentile(e2e, 95),
                "mean_ms": mean(e2e), "share_mean_pct": 100.0, "share_p50_pct": 100.0})
    return out


def dominant(table: List[dict]) -> dict:
    path = [r for r in table if r["stage"] in {n for n, _ in STAGES} and not r["stage"].startswith("Other")]
    return max(path, key=lambda r: r["share_mean_pct"])


def main() -> int:
    print(BANNER, flush=True)
    runs = [json.loads(x) for x in RUNS.read_text(encoding="utf-8").splitlines() if x.strip()] if RUNS.exists() else []
    misses = [r for r in runs if r["phase"] == "miss" and r["kind_result"] == "confirmed_miss"]
    hits = [r for r in runs if r["phase"] == "hit" and r["kind_result"] == "hit"]
    by_trace: Dict[str, List[dict]] = {}
    for s in read_spans(DEFAULT_PATH):
        by_trace.setdefault(s["trace_id"], []).append(s)
    rows, missing = [], []
    for r in misses:
        row = per_request(r["trace_id"], by_trace.get(r["trace_id"], []))
        (rows.append(row) if row else missing.append(r["trace_id"]))
    print(f"confirmed misses in the run log: {len(misses)}; with a complete span set: {len(rows)}; incomplete: {len(missing)}")
    if not rows:
        return 1
    table = summarize(rows)
    print("\nCache-miss stage latency (ms)")
    print(f"{'Stage':50s} {'n':>3s} {'p50':>10s} {'p95':>10s} {'mean':>10s} {'% e2e (mean)':>13s} {'% e2e (p50)':>12s}")
    for t in table:
        print(f"{t['stage']:50s} {t['n']:3d} {t['p50_ms']:10.1f} {t['p95_ms']:10.1f} {t['mean_ms']:10.1f} "
              f"{t['share_mean_pct']:12.1f}% {t['share_p50_pct']:11.1f}%")
    d = dominant(table)
    print(f"\ndominant contributor on the request path: {d['stage']} ({d['share_mean_pct']:.1f}% of mean end-to-end)")
    hit_rows = []
    for r in hits:
        sp = by_trace.get(r["trace_id"], [])
        req = [s["duration_ms"] for s in sp if s["stage"] == "request"]
        look = [s["duration_ms"] for s in sp if s["stage"] == "cache_lookup"]
        if req and look:
            hit_rows.append({"trace_id": r["trace_id"], "end_to_end_ms": req[0], "cache_lookup_ms": look[0]})
    hit_summary = None
    if hit_rows:
        he = [h["end_to_end_ms"] for h in hit_rows]
        hit_summary = {"n": len(he), "p50_ms": percentile(he, 50), "p95_ms": percentile(he, 95), "mean_ms": mean(he)}
        print(f"cache-hit latency (separate metric): n={len(he)} p50={hit_summary['p50_ms']:.1f} ms  p95={hit_summary['p95_ms']:.1f} ms")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "latency_table.json").write_text(json.dumps({"misses": table, "hits": hit_summary, "n_requests": len(rows),
                                                        "incomplete_traces": missing, "dominant": d["stage"]}, indent=2), encoding="utf-8")
    with (OUT / "latency_table.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["stage", "n", "p50_ms", "p95_ms", "mean_ms", "share_of_mean_e2e_pct", "share_p50_pct"])
        for t in table:
            w.writerow([t["stage"], t["n"], round(t["p50_ms"], 1), round(t["p95_ms"], 1), round(t["mean_ms"], 1),
                        round(t["share_mean_pct"], 1), round(t["share_p50_pct"], 1)])
    with (OUT / "latency_per_request.csv").open("w", newline="", encoding="utf-8") as fh:
        keys = ["trace_id", "cache_lookup_ms", "planner_ms", "writer_ms", "reviewer_ms", "queue_wait_ms", "other_ms",
                "end_to_end_ms", "evaluation_ms"]
        w = csv.writer(fh)
        w.writerow(keys)
        for r in rows:
            w.writerow([r["trace_id"]] + [("" if r[k] is None else round(r[k], 3)) for k in keys[1:]])
    print(f"wrote {(OUT / 'latency_table.json').relative_to(REPO)}, latency_table.csv, latency_per_request.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
