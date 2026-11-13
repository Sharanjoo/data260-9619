"""HW10 Part 4.3: latency statistics over spans, shared by scripts/hw10_latency_report.py and the dashboard.

Percentiles use linear interpolation between ranks (numpy's default). Shares are mean stage time / mean end-to-end time."""
from __future__ import annotations

from typing import Dict, List, Optional

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
