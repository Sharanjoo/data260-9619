"""HW10 Part 4.3 offline checks for the latency statistics (python scripts/test_hw10_latency.py)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from hw10_latency_report import dominant, per_request, percentile, summarize  # noqa: E402

passed = failed = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global passed, failed
    passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))


def spans(tid, look, plan, write, review, waits, extra=0.0, ev=None):
    s = [{"trace_id": tid, "stage": "cache_lookup", "duration_ms": look}, {"trace_id": tid, "stage": "planner", "duration_ms": plan},
         {"trace_id": tid, "stage": "writer", "duration_ms": write}, {"trace_id": tid, "stage": "reviewer", "duration_ms": review}]
    s += [{"trace_id": tid, "stage": f"queue_wait_{n}", "duration_ms": w} for n, w in zip(("inbox", "tasks", "drafts", "final"), waits)]
    total = look + plan + write + review + sum(waits) + extra
    s.append({"trace_id": tid, "stage": "request", "duration_ms": total})
    if ev is not None:
        s.append({"trace_id": tid, "stage": "evaluator", "duration_ms": ev})
    return s


xs = [1, 2, 3, 4, 5]
check("percentile: p50 of 1..5 is 3, p95 is 4.8, p0/p100 are the ends", (percentile(xs, 50), round(percentile(xs, 95), 6),
      percentile(xs, 0), percentile(xs, 100)) == (3, 4.8, 1, 5))
check("percentile: even count interpolates (p50 of 1..4 is 2.5)", percentile([4, 1, 3, 2], 50) == 2.5)
check("percentile: one value", percentile([7.0], 95) == 7.0)
r = per_request("t", spans("t", 100, 40000, 30000, 20000, [50, 20, 20, 10], extra=300, ev=90000))
check("per_request: stages, summed queue wait, other and evaluation", r["queue_wait_ms"] == 100 and abs(r["other_ms"] - 300) < 1e-9
      and r["evaluation_ms"] == 90000 and r["end_to_end_ms"] == 100 + 40000 + 30000 + 20000 + 100 + 300)
check("per_request: a missing stage gives None", per_request("t", spans("t", 1, 2, 3, 4, [1, 1, 1, 1])[:-2]) is None)
retry = spans("t", 100, 100, 1000, 20000, [1, 1, 1, 1])
retry.append({"trace_id": "t", "stage": "writer", "duration_ms": 500})
check("per_request: retried stage durations are summed", per_request("t", retry)["writer_ms"] == 1500)
rows = [per_request(f"t{i}", spans(f"t{i}", 100, 40000 + i, 30000, 25000, [10, 10, 10, 10], 200, 80000)) for i in range(50)]
tab = summarize(rows)
by = {t["stage"]: t for t in tab}
check("summarize: planner is the dominant request-path stage", dominant(tab)["stage"] == "Planner")
check("summarize: shares of the request-path stages add up to 100%", abs(sum(
    t["share_mean_pct"] for t in tab if t["stage"] not in ("End-to-end (cache miss)",) and not t["stage"].startswith("Evaluation")) - 100) < 1e-6)
check("summarize: evaluation row present and outside the request path", any(t["stage"].startswith("Evaluation") for t in tab))
check("summarize: end-to-end row is the sum", abs(by["End-to-end (cache miss)"]["p50_ms"] - (100 + 40024.5 + 30000 + 25000 + 40 + 200)) < 1)
print(f"\n{passed} passed, {failed} failed")
sys.exit(0 if failed == 0 else 1)
