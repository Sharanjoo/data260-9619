"""HW10 Part 1 offline checks (python scripts/test_hw10_dashboard.py): the dashboard's numbers and the three pages, on a
small synthetic log set (a cache hit, a cache miss, a failed request and a request with the cache bypassed)."""
from __future__ import annotations

import csv
import json
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "code"))

from dashboard import data  # noqa: E402

passed = failed = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global passed, failed
    passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))


NOW = time.time() * 1000
SP = []


def span(tid, stage, start_s, dur_s, status="ok", error=None, **attrs):
    st = NOW - 600_000 + start_s * 1000
    SP.append({"trace_id": tid, "stage": stage, "start": "t0", "end": "t1", "start_ms": st, "end_ms": st + dur_s * 1000,
               "duration_ms": dur_s * 1000, "status": status, "error": error, "attrs": attrs})


HIT, MISS, FAIL, BYP = "hit-1", "miss-1", "fail-1", "bypass-1"
span(HIT, "cache_lookup", 0, 0.1, hit=True, similarity=0.99)
span(HIT, "request", 0, 0.12, is_cached=True, answer_status="cached", similarity=0.99)
t = 10
span(MISS, "cache_lookup", t, 0.1, hit=False, similarity=0.2)
for name, off, d in (("queue_wait_inbox", 0.1, 0.05), ("planner", 0.15, 40), ("queue_wait_tasks", 40.15, 0.02), ("writer", 40.2, 30),
                     ("queue_wait_drafts", 70.2, 0.02), ("reviewer", 70.3, 20), ("queue_wait_final", 90.3, 0.02)):
    span(MISS, name, t + off, d)
span(MISS, "agent_pipeline", t + 0.1, 90.3)
span(MISS, "request", t, 91, is_cached=False, answer_status="approved", similarity=0.2)
t = 200
span(FAIL, "cache_lookup", t, 0.1, hit=False, similarity=0.1)
span(FAIL, "queue_wait_inbox", t + 0.1, 0.05)
span(FAIL, "planner", t + 0.15, 40)
span(FAIL, "queue_wait_tasks", t + 40.2, 0.02)
for k in range(3):
    span(FAIL, "writer", t + 40.3 + k, 0.4, "error", "ModelClientError: HTTP 404 model not found", attempt=k + 1)
span(FAIL, "dead_letter", t + 44, 0.01, "error", "gave up after 3 attempts", failed_stage="writer")
span(FAIL, "agent_pipeline", t + 0.1, 180, "timeout", "no final message before the agent timeout")
span(FAIL, "request", t, 180.2, "error", "request ended with status=timeout", is_cached=False, answer_status="timeout", similarity=0.1)
span(BYP, "planner", 300, 10)
span(BYP, "request", 300, 11, is_cached=False, answer_status="approved", similarity=None)

tmp = Path(tempfile.mkdtemp(prefix="hw10_dash_"))
(tmp / "spans.jsonl").write_text("\n".join(json.dumps(s) for s in SP), encoding="utf-8")
(tmp / "latency_runs.jsonl").write_text("\n".join(json.dumps(r) for r in (
    {"phase": "miss", "kind_result": "confirmed_miss", "trace_id": MISS}, {"phase": "hit", "kind_result": "hit", "trace_id": HIT})), encoding="utf-8")
(tmp / "failed_trace.json").write_text(json.dumps({"trace_id": FAIL}), encoding="utf-8")
ev = {"trace_id": MISS, "question": "What now?", "status": "ok", "judge_model": "j", "scores": {
    "plan_quality": {"score": 3, "reason": "plan", "error": None}, "writer_helpfulness": {"score": 4, "reason": "draft", "error": None},
    "final_helpfulness": {"score": 4, "reason": "final", "error": None}},
    "improvement": {"draft_score": 4, "final_score": 4, "difference": 0, "identical_text": True, "interpretation": "no change"},
    "inputs": {"final_answer": "Do not eat it."}}
(tmp / "evaluations.jsonl").write_text(json.dumps(ev) + "\nnot json\n", encoding="utf-8")
(tmp / "judge_validation.json").write_text(json.dumps({"agreement_run1": {"n": 20, "spearman": 0.5, "mean_abs_diff": 1.0,
    "mean_signed_diff_judge_minus_human": -0.5, "within_1": 0.8}, "repeatability": {"runs": [1, 2, 3], "n_cases": 20, "cases_changed": 4,
    "fraction_changed": 0.2, "mean_abs_change_between_runs": 0.1, "max_abs_change_between_runs": 1}}), encoding="utf-8")
with (tmp / "per_case.csv").open("w", newline="", encoding="utf-8") as fh:
    w = csv.writer(fh)
    w.writerow(["case_id", "human_label", "judge_run1"])
    w.writerow(["C01", 3, 4])
data.SPANS, data.EVALS, data.VALIDATION, data.PER_CASE = tmp / "spans.jsonl", tmp / "evaluations.jsonl", tmp / "judge_validation.json", tmp / "per_case.csv"
data.LATENCY_RUNS, data.FAILED = tmp / "latency_runs.jsonl", tmp / "failed_trace.json"

spans = data.read_jsonl(data.SPANS)
rows = data.requests_from_spans(spans)
s = data.summarize_requests(rows)
check("summary: 4 requests, 3 through the cache and 1 bypassed", (s["requests"], s["cache_enabled"], s["cache_bypassed"]) == (4, 3, 1), str(s["requests"]))
check("summary: hit rate 1/3 and miss rate 2/3 over the cache requests only", s["hits"] == 1 and s["misses"] == 2
      and abs(s["hit_rate"] - 1 / 3) < 1e-9 and abs(s["miss_rate"] - 2 / 3) < 1e-9)
check("summary: error rate is 1 of 4 and the failed trace is listed", s["errors"] == 1 and abs(s["error_rate"] - 0.25) < 1e-9 and s["error_trace_ids"] == [FAIL])
check("summary: hit latency is separate and fast, miss latency is slow", s["latency_hit"]["p50_ms"] < 1000 < s["latency_miss"]["p50_ms"])
check("summary: stage error spans (retries) are counted for the window", len(data.stage_error_spans(spans, rows)) == 5)
check("window: last 1 hour keeps all; a window that ends before the data keeps none",
      len(data.in_window(rows, NOW, 3600)) == 4 and len(data.in_window(rows, NOW + 10_000_000, 3600)) == 0)
check("window: None keeps everything", len(data.in_window(rows, NOW, None)) == 4)

j = data.journey(spans, MISS)
check("trace: miss path, stages in start order, total from the request span", j["path"] == "CACHE MISS" and [r["stage"] for r in j["rows"] if r["scope"] == "stage"][:3] == ["cache_lookup", "queue_wait_inbox", "planner"]
      and abs(j["total_ms"] - 91000) < 1)
check("trace: every row has start, end, duration, status and error fields", all(k in j["rows"][0] for k in ("start", "end", "duration_ms", "status", "error")))
jh = data.journey(spans, HIT)
check("trace: hit path has only cache_lookup and request", jh["path"] == "CACHE HIT" and sorted(r["stage"] for r in jh["rows"]) == ["cache_lookup", "request"])
jf = data.journey(spans, FAIL)
check("trace: failed request shows the failing stage, the error and the dead letter", jf["failing_stage"] == "writer"
      and "404" in jf["failing_error"] and jf["has_dead_letter"] and jf["request_status"] == "error")
check("trace: an unknown id is reported as not found", data.journey(spans, "nope")["found"] is False)
check("trace: surrounding spaces in the pasted id are ignored", data.journey(spans, f"  {MISS} ")["found"])
check("trace: a request with no cache_lookup says the cache was not used", "not used" in data.journey(spans, BYP)["path"])

res = data.latest_evaluations(data.read_jsonl(data.EVALS))
check("evaluation: bad log lines are skipped, one result", len(res) == 1)
check("evaluation: scores by stage", [r["mean_score"] for r in data.stage_scores(res)] == [3, 4, 4])
check("evaluation: interpretation mentions the Reviewer passing drafts through", any("word for word" in x for x in data.interpretation(res)))
check("evaluation: empty results give a hint, not an error", "No evaluation results" in data.interpretation([])[0])

try:
    from streamlit.testing.v1 import AppTest
except ImportError:
    print("[SKIP] page rendering (streamlit is not installed here)")
else:
    def run(module: str):
        script = f"import sys\nsys.path.insert(0, {str(REPO)!r})\nsys.path.insert(0, {str(REPO / 'code')!r})\n" \
                 f"from dashboard import {module}\n{module}.render()\n"
        at = AppTest.from_string(script, default_timeout=60)
        at.run()
        return at

    at = run("view_summary")
    check("page Summary renders with no exception", not at.exception, str([e.value for e in at.exception]))
    labels = {m.label: m.value for m in at.metric}
    check("page Summary shows requests, hit rate, error rate and latency", labels.get("Requests") == "4" and labels.get("Cache hit rate") == "33%"
          and labels.get("Error rate") == "25.0%" and "End-to-end latency p95 (all)" in labels, str(labels))
    check("page Summary states the window and the data source for each metric", sum("Source: reports/hw10/raw/spans.jsonl" in c.value and "Window:" in c.value for c in at.caption) >= 3)
    at = run("view_trace")
    check("page Trace lookup renders and asks for an id", not at.exception and any("Enter a trace_id" in i.value for i in at.info))
    at.text_input[0].set_value(FAIL).run()
    check("page Trace lookup: the failed trace shows the failing stage", not at.exception and any("FAILED request" in e.value and "writer" in e.value for e in at.error))
    at.text_input[0].set_value(HIT).run()
    check("page Trace lookup: a hit trace shows the CACHE HIT path", any("CACHE HIT" in e.value for e in at.success))
    at.text_input[0].set_value(MISS).run()
    check("page Trace lookup: a miss trace shows the CACHE MISS path", any("CACHE MISS" in e.value for e in at.info))
    at = run("view_evaluation")
    labels = {m.label: m.value for m in at.metric}
    check("page Evaluation renders Part 2 and the Part 3 validation figures", not at.exception and labels.get("Spearman correlation") == "0.50"
          and labels.get("Mean absolute difference") == "1.00", str(labels))
print(f"\n{passed} passed, {failed} failed")
sys.exit(0 if failed == 0 else 1)
