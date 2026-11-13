"""HW10 Part 1: everything the dashboard shows, computed from the saved logs by plain functions (no Streamlit import, so it is
unit-tested offline). Sources, all written by the earlier parts:

    reports/hw10/raw/spans.jsonl                 one JSON span per stage (trace_id = HW8 correlation_id)          Parts 1.1, 1.3
    reports/hw10/raw/evaluations.jsonl           Part 2 judge results per request                                  Part 1.2
    reports/hw10/raw/judge_validation.json       Part 3 Spearman / mean abs difference / repeatability             Part 1.2
    reports/hw10/raw/judge_validation_per_case.csv, judge_runs.csv   Part 3 raw per-case data                      Part 1.2
    data/hw10/latency_runs.jsonl, failed_trace.json   which trace ids are the hit / miss / failed examples        Part 1.3
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "code"))

from tracing.stats import mean, percentile  # noqa: E402

RAW = REPO / "reports" / "hw10" / "raw"
DATA = REPO / "data" / "hw10"
SPANS = RAW / "spans.jsonl"
EVALS = RAW / "evaluations.jsonl"
VALIDATION = RAW / "judge_validation.json"
PER_CASE = RAW / "judge_validation_per_case.csv"
LATENCY_RUNS = DATA / "latency_runs.jsonl"
FAILED = DATA / "failed_trace.json"
BANNER = "Sharan Lourduraj | SID4 9619 | DATA 260 HW10"
WINDOWS = {"Last 1 hour": 3600, "Last 24 hours": 86400, "Last 7 days": 7 * 86400, "All data in the file": None}


def read_jsonl(path: Path) -> List[dict]:
    out: List[dict] = []
    if not Path(path).exists():
        return out
    with Path(path).open(encoding="utf-8") as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if isinstance(rec, dict):
                out.append(rec)
    return out


def read_json(path: Path) -> Optional[dict]:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def read_csv(path: Path) -> List[dict]:
    if not Path(path).exists():
        return []
    with Path(path).open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


# ---------- Part 1.1 summary ----------
def requests_from_spans(spans: List[dict]) -> List[dict]:
    """One row per request: the 'request' span the ingress writes for every call (hit, miss or failed)."""
    rows = []
    with_lookup = {s["trace_id"] for s in spans if s.get("stage") == "cache_lookup"}
    for s in spans:
        if s.get("stage") != "request":
            continue
        a = s.get("attrs") or {}
        rows.append({"trace_id": s["trace_id"], "cache_enabled": s["trace_id"] in with_lookup, "start_ms": s["start_ms"], "end_ms": s["end_ms"], "latency_ms": s["duration_ms"],
                     "is_cached": bool(a.get("is_cached")), "status": s["status"], "answer_status": a.get("answer_status"),
                     "error": s.get("error"), "tag": a.get("tag"), "similarity": a.get("similarity")})
    return sorted(rows, key=lambda r: r["start_ms"])


def in_window(rows: List[dict], now_ms: float, seconds: Optional[float]) -> List[dict]:
    return rows if seconds is None else [r for r in rows if r["start_ms"] >= now_ms - seconds * 1000]


def _lat(rows: List[dict]) -> Dict[str, Optional[float]]:
    xs = [r["latency_ms"] for r in rows]
    if not xs:
        return {"n": 0, "p50_ms": None, "p95_ms": None, "mean_ms": None}
    return {"n": len(xs), "p50_ms": percentile(xs, 50), "p95_ms": percentile(xs, 95), "mean_ms": mean(xs)}


def summarize_requests(rows: List[dict]) -> Dict[str, Any]:
    """Hit and miss figures use only requests that went through the cache (a cache_lookup span exists); requests that bypassed
    the cache (use_cache=False, e.g. the Part 3 drafts) are counted separately so they cannot dilute the hit rate."""
    cached = [r for r in rows if r["cache_enabled"]]
    hits = [r for r in cached if r["is_cached"]]
    misses = [r for r in cached if not r["is_cached"]]
    errors = [r for r in rows if r["status"] != "ok"]
    n, nc = len(rows), len(cached)
    return {"requests": n, "cache_enabled": nc, "cache_bypassed": n - nc, "hits": len(hits), "misses": len(misses),
            "hit_rate": len(hits) / nc if nc else None, "miss_rate": len(misses) / nc if nc else None,
            "errors": len(errors), "error_rate": len(errors) / n if n else None,
            "error_trace_ids": [r["trace_id"] for r in errors], "latency_all": _lat(rows), "latency_hit": _lat(hits),
            "latency_miss": _lat(misses),
            "first_request_ms": rows[0]["start_ms"] if rows else None, "last_request_ms": rows[-1]["end_ms"] if rows else None}


def stage_error_spans(spans: List[dict], rows: List[dict]) -> List[dict]:
    """Error spans of the stages (planner, writer, ...) that belong to the requests in the window (retries included)."""
    ids = {r["trace_id"] for r in rows}
    return [s for s in spans if s["trace_id"] in ids and s.get("status") != "ok" and s["stage"] != "request"]


# ---------- Part 1.3 trace lookup ----------
ORDER_NOTE = "ordered by start time"


def journey(spans: List[dict], trace_id: str) -> Dict[str, Any]:
    mine = sorted((s for s in spans if s["trace_id"] == trace_id.strip()), key=lambda s: (s["start_ms"], -s["end_ms"]))  # a span that contains others comes first
    if not mine:
        return {"found": False, "trace_id": trace_id.strip()}
    t0 = mine[0]["start_ms"]
    lookup = next((s for s in mine if s["stage"] == "cache_lookup"), None)
    if lookup is None:
        path = "cache not used (no cache_lookup span)"
    else:
        path = "CACHE HIT" if (lookup.get("attrs") or {}).get("hit") else "CACHE MISS"
    request = next((s for s in mine if s["stage"] == "request"), None)
    failing = next((s for s in mine if s["status"] != "ok" and s["stage"] in ("planner", "writer", "reviewer")), None)
    scope = {"request": "whole request", "agent_pipeline": "whole agent path"}
    rows = [{"order": i + 1, "stage": s["stage"], "scope": scope.get(s["stage"], "stage"), "start": s["start"], "end": s["end"], "duration_ms": s["duration_ms"],
             "status": s["status"], "error": s.get("error") or "", "start_offset_ms": s["start_ms"] - t0,
             "end_offset_ms": s["end_ms"] - t0, "details": json.dumps(s.get("attrs") or {}, ensure_ascii=False)}
            for i, s in enumerate(mine)]
    return {"found": True, "trace_id": trace_id.strip(), "path": path, "rows": rows,
            "request_status": request["status"] if request else None,
            "total_ms": request["duration_ms"] if request else (mine[-1]["end_ms"] - t0),
            "failing_stage": failing["stage"] if failing else None, "failing_error": failing["error"] if failing else None,
            "has_dead_letter": any(s["stage"] == "dead_letter" for s in mine)}


def example_traces() -> Dict[str, Optional[str]]:
    """The three traces the report uses: one cache hit, one successful cache miss, one failed request."""
    runs = read_jsonl(LATENCY_RUNS)
    hit = next((r["trace_id"] for r in runs if r.get("kind_result") == "hit"), None)
    miss = next((r["trace_id"] for r in runs if r.get("kind_result") == "confirmed_miss"), None)
    failed = (read_json(FAILED) or {}).get("trace_id")
    return {"cache_hit": hit, "cache_miss": miss, "failed": failed}


# ---------- Part 1.2 evaluation ----------
def latest_evaluations(evals: List[dict]) -> List[dict]:
    """The newest result per trace_id."""
    out: Dict[str, dict] = {}
    for r in evals:
        if r.get("trace_id"):
            out[r["trace_id"]] = r
    return list(out.values())


def stage_scores(results: List[dict]) -> List[dict]:
    names = (("Planner (plan quality)", "plan_quality"), ("Writer (draft helpfulness)", "writer_helpfulness"),
             ("Reviewer (final answer helpfulness)", "final_helpfulness"))
    rows = []
    for label, key in names:
        xs = [r["scores"][key]["score"] for r in results if r.get("scores", {}).get(key, {}).get("score") is not None]
        rows.append({"stage": label, "n": len(xs), "mean_score": mean(xs) if xs else None, "min": min(xs) if xs else None,
                     "max": max(xs) if xs else None})
    return rows


def case_table(results: List[dict]) -> List[dict]:
    rows = []
    for r in results:
        s, imp = r.get("scores", {}), r.get("improvement", {})
        rows.append({"trace_id": r["trace_id"], "question": (r.get("question") or "")[:90],
                     "plan_quality": s.get("plan_quality", {}).get("score"),
                     "writer_helpfulness": s.get("writer_helpfulness", {}).get("score"),
                     "final_helpfulness": s.get("final_helpfulness", {}).get("score"), "difference": imp.get("difference"),
                     "final_equals_draft": imp.get("identical_text"), "status": r.get("status")})
    return rows


def interpretation(results: List[dict]) -> List[str]:
    """Plain-language reading of the Part 2 scores, computed from the numbers (no model)."""
    if not results:
        return ["No evaluation results yet: run scripts/hw10_evaluate.py."]
    ss = {s["stage"].split(" ")[0]: s for s in stage_scores(results)}
    lines = []
    p, w, f = ss["Planner"]["mean_score"], ss["Writer"]["mean_score"], ss["Reviewer"]["mean_score"]
    if None not in (p, w, f):
        lines.append(f"Mean judge scores over {len(results)} request(s): Planner {p:.2f}, Writer {w:.2f}, Reviewer {f:.2f} (1-5).")
        weakest = min((("Planner", p), ("Writer", w), ("Reviewer", f)), key=lambda x: x[1])
        lines.append(f"The lowest-scoring stage is the {weakest[0]}.")
    diffs = [r["improvement"]["difference"] for r in results if r.get("improvement", {}).get("difference") is not None]
    same = sum(1 for r in results if r.get("improvement", {}).get("identical_text"))
    if diffs:
        lines.append(f"Final minus draft: mean {mean(diffs):+.2f}, range {min(diffs):+d} to {max(diffs):+d}. In {same} of "
                     f"{len(results)} request(s) the Reviewer passed the Writer's draft through word for word, so the Reviewer "
                     "approves or rejects but does not improve the answer; any non-zero difference on identical text is judge noise.")
    return lines


def validation_summary() -> Optional[dict]:
    return read_json(VALIDATION)
