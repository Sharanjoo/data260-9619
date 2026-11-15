"""HW10 self-check (make verify-hw10): offline test suites plus the saved evidence for every part, re-derived from the raw files.

Offline suites: test_agents_hw08.py, test_hw9_cache.py, test_hw10_tracing.py, test_hw10_evaluator.py, test_hw10_latency.py,
test_hw10_judge_validate.py, test_hw10_dashboard.py (a scripted judge and in-memory Kafka stand in for Ollama and Kafka).
Saved evidence, recomputed from the raw logs rather than trusted:
  Part 1  dashboard files, Part 2 one evaluated request joined by correlation_id, Part 3 20 cases + 20 hand labels committed
  BEFORE the first judge score, Spearman / mean abs difference / repeatability recomputed from the raw per-case rows,
  Part 4 spans on every stage with one trace_id, a cache-hit, a cache-miss and a failed trace, 50 confirmed misses and the
  percentile table recomputed from the per-request rows.
It does NOT modify application code: it hashes code/ and src/ before and after.

Usage (repo root):   python scripts/verify_hw10.py            (writes reports/hw10/verification.json)
                     python scripts/verify_hw10.py --skip-suites"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REPORT_DIR = REPO_ROOT / "reports" / "hw10"
RAW = REPORT_DIR / "raw"
DATA = REPO_ROOT / "data" / "hw10"
sys.path.insert(0, str(REPO_ROOT / "code"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from cache_layer.config import PORT_BASE, SEED, SID4, VERIFY_SEED  # noqa: E402
from tracing.spans import read_spans  # noqa: E402
from tracing.stats import summarize  # noqa: E402

HOMEWORK_NUMBER = 10
THRESHOLD = 0.95
MODEL_CONFIG = ("Pipeline: HW8 Planner, Writer, Reviewer with qwen3:8b via Ollama behind the HW9 Redis semantic cache (threshold 0.95). "
                "Judge: DeepEval GEval on a local Ollama qwen3:8b, temperature 0, thinking off, fixed evaluation steps, 1-5 rubric. "
                "Tracing: trace_id = the HW8 correlation_id, one JSON span per stage in reports/hw10/raw/spans.jsonl")
checks: list = []
info: dict = {}


def record(name: str, passed: bool, detail: str = "") -> None:
    checks.append({"check": name, "passed": bool(passed), "detail": detail})
    print(f"[{'PASS' if passed else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""), flush=True)


def git(*args: str) -> str:
    try:
        return subprocess.check_output(["git", *args], cwd=REPO_ROOT, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:  # noqa: BLE001
        return ""


def tree_hash(*folders: str) -> str:
    digest = hashlib.sha256()
    for folder in folders:
        for path in sorted((REPO_ROOT / folder).rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
                digest.update(str(path.relative_to(REPO_ROOT)).encode())
                digest.update(path.read_bytes())
    return digest.hexdigest()


def jl(path: Path) -> list:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def run_script(label: str, script: str, timeout: int = 900) -> None:
    try:
        p = subprocess.run([sys.executable, str(REPO_ROOT / "scripts" / script)], cwd=REPO_ROOT, capture_output=True, text=True, timeout=timeout)
        lines = [ln for ln in p.stdout.strip().splitlines() if ln.strip()]
        last = lines[-1] if lines else (p.stderr.strip().splitlines() or ["no output"])[-1]
        skipped = [ln for ln in lines if ln.startswith("[SKIP]")]
        record(label, p.returncode == 0 and not skipped, last[:140] + (f" (SKIPPED: {skipped[0][:60]})" if skipped else ""))
    except Exception as exc:  # noqa: BLE001
        record(label, False, f"{type(exc).__name__}: {exc}")


def check_suites() -> None:
    for script in ("test_agents_hw08.py", "test_hw9_cache.py", "test_hw10_tracing.py", "test_hw10_evaluator.py", "test_hw10_latency.py",
                   "test_hw10_judge_validate.py", "test_hw10_dashboard.py"):
        run_script(f"suite_{script[:-3]}", script)


def check_part1() -> None:
    files = ["app.py", "data.py", "loaders.py", "view_summary.py", "view_evaluation.py", "view_trace.py"]
    missing = [f for f in files if not (REPO_ROOT / "dashboard" / f).exists()]
    record("part1_dashboard_files_present", not missing, "missing: " + ", ".join(missing) if missing else f"dashboard/{{{', '.join(files)}}}")
    text = "".join((REPO_ROOT / "dashboard" / f).read_text(encoding="utf-8") for f in files if (REPO_ROOT / "dashboard" / f).exists())
    record("part1_uses_streamlit_caching", "st.cache_data" in text and "st.cache_resource" in text, "st.cache_data and st.cache_resource used")
    record("part1_summary_states_window_and_source", "Window:" in text and "Source:" in text, "every summary metric caption carries Window and Source")
    record("part1_three_pages_registered", all(k in (REPO_ROOT / "dashboard" / "app.py").read_text(encoding="utf-8") for k in ("Summary", "Evaluation", "Trace lookup")), "")


def check_part2() -> None:
    ev = [r for r in jl(RAW / "evaluations.jsonl") if r.get("status") == "ok"]
    bundles = {b["trace_id"]: b for b in jl(RAW / "bundles.jsonl") if not b.get("missing")}
    spans = read_spans(RAW / "spans.jsonl")
    record("part2_at_least_one_end_to_end_request_evaluated", bool(ev), f"{len(ev)} evaluated requests with status ok")
    if not ev:
        return
    ok = [r for r in ev if r["trace_id"] in bundles]
    record("part2_plan_draft_final_joined_by_correlation_id", bool(ok), f"{len(ok)} of {len(ev)} results have a bundle with plan, draft and final")
    r = ok[0] if ok else ev[0]
    b = bundles.get(r["trace_id"], {})
    msgs = b.get("messages", {})
    record("part2_original_message_content_and_metadata_kept", all(p in msgs and msgs[p].get("correlation_id") == r["trace_id"] for p in ("plan", "draft", "final"))
           and all(k in b.get("kafka", {}).get("draft", {}) for k in ("topic", "partition", "offset")), f"trace {r['trace_id']}")
    scores = [r["scores"][k]["score"] for k in ("plan_quality", "writer_helpfulness", "final_helpfulness")]
    record("part2_all_scores_on_the_1_to_5_scale_with_reasons", all(isinstance(s, int) and 1 <= s <= 5 for s in scores)
           and all(r["scores"][k]["reason"] for k in r["scores"]), f"plan/writer/final = {scores}")
    imp = r["improvement"]
    record("part2_final_vs_draft_has_both_scores_difference_and_interpretation", imp["difference"] == imp["final_score"] - imp["draft_score"]
           and bool(imp["interpretation"]), f"draft {imp['draft_score']}, final {imp['final_score']}, difference {imp['difference']}")
    record("part2_writer_score_carries_trace_id_and_final_the_answer", r.get("writer_helpfulness_trace_id") == r["trace_id"] and bool(r["inputs"]["final_answer"]), "")
    record("part2_evaluator_span_written_for_the_same_trace_id", any(s["stage"] == "evaluator" and s["trace_id"] == r["trace_id"] for s in spans), "")


def check_part3() -> None:
    cases_f, labels_f = DATA / "eval_cases.json", DATA / "human_labels.csv"
    cases = json.loads(cases_f.read_text(encoding="utf-8"))["cases"] if cases_f.exists() else []
    labels = {}
    if labels_f.exists():
        with labels_f.open(encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh):
                if (row.get("human_label") or "").strip().isdigit():
                    labels[row["case_id"]] = int(row["human_label"])
    record("part3_20_cases_and_20_whole_number_labels", len(cases) == 20 and len(labels) == 20 and all(1 <= v <= 5 for v in labels.values())
           and sorted(labels) == sorted(c["case_id"] for c in cases), f"{len(cases)} cases, {len(labels)} labels")
    runs_f = RAW / "judge_runs.csv"
    runs = list(csv.DictReader(runs_f.open(encoding="utf-8", newline=""))) if runs_f.exists() else []
    clean = git("status", "--porcelain", "--", "data/hw10/eval_cases.json", "data/hw10/human_labels.csv") == ""
    commit_time = git("log", "-1", "--format=%cI", "--", "data/hw10/eval_cases.json", "data/hw10/human_labels.csv")
    commit = git("log", "-1", "--format=%H", "--", "data/hw10/eval_cases.json", "data/hw10/human_labels.csv")
    first = min((r["scored_at"] for r in runs), default="")
    before = bool(commit_time) and bool(first) and datetime.fromisoformat(commit_time) < datetime.fromisoformat(first + ("+00:00" if "+" not in first else ""))
    record("part3_cases_and_labels_committed_before_the_first_judge_score_and_unchanged", clean and before and all(r["labels_commit"] == commit for r in runs),
           f"commit {commit[:8]} at {commit_time}; first judge score {first}; working copy clean={clean}")
    by_run: dict = {}
    for r in runs:
        if r["judge_score"] != "":
            by_run.setdefault(int(r["run"]), {})[r["case_id"]] = int(r["judge_score"])
    record("part3_judge_run_three_times_on_all_20_drafts", sorted(by_run) == [1, 2, 3] and all(len(v) == 20 for v in by_run.values()),
           f"scored cases per run: { {k: len(v) for k, v in by_run.items()} }")
    val_f = RAW / "judge_validation.json"
    if not val_f.exists() or sorted(by_run) != [1, 2, 3]:
        record("part3_statistics_recomputed_from_the_raw_rows", False, "raw/judge_validation.json missing (python scripts/hw10_judge_validate.py stats)")
        return
    import hw10_judge_validate as hv  # noqa: PLC0415

    saved = json.loads(val_f.read_text(encoding="utf-8"))
    a = hv.agreement(labels, by_run[1])
    rep = hv.repeatability(by_run)
    sp_saved = saved["agreement_run1"]["spearman"]
    same = (abs((sp_saved if sp_saved is not None else 9) - (a["spearman"] if a["spearman"] is not None else 9)) < 1e-9
            and abs(saved["agreement_run1"]["mean_abs_diff"] - a["mean_abs_diff"]) < 1e-9
            and abs(saved["repeatability"]["fraction_changed"] - rep["fraction_changed"]) < 1e-9
            and abs(saved["repeatability"]["mean_abs_change_between_runs"] - rep["mean_abs_change_between_runs"]) < 1e-9
            and saved["repeatability"]["max_abs_change_between_runs"] == rep["max_abs_change_between_runs"])
    record("part3_statistics_recomputed_from_the_raw_rows", same,
           f"Spearman {a['spearman']}, mean abs diff {a['mean_abs_diff']:.2f}, changed {rep['cases_changed']}/20, mean/max change "
           f"{rep['mean_abs_change_between_runs']:.2f}/{rep['max_abs_change_between_runs']}")
    info["judge_validation"] = {"spearman": a["spearman"], "mean_abs_diff": a["mean_abs_diff"], "bias": a["mean_signed_diff_judge_minus_human"],
                                "fraction_changed": rep["fraction_changed"], "mean_abs_change": rep["mean_abs_change_between_runs"],
                                "max_abs_change": rep["max_abs_change_between_runs"]}


def check_part4() -> None:
    spans = read_spans(RAW / "spans.jsonl")
    need = ("trace_id", "stage", "start", "end", "status", "error")
    record("part4_every_span_has_trace_id_stage_start_end_status_error", bool(spans) and all(all(k in s for k in need) for s in spans), f"{len(spans)} spans")
    by: dict = {}
    for s in spans:
        by.setdefault(s["trace_id"], []).append(s)
    runs = jl(DATA / "latency_runs.jsonl")
    hit = next((r["trace_id"] for r in runs if r.get("kind_result") == "hit"), None)
    miss = next((r["trace_id"] for r in runs if r.get("kind_result") == "confirmed_miss"), None)
    failed_doc = json.loads((DATA / "failed_trace.json").read_text(encoding="utf-8")) if (DATA / "failed_trace.json").exists() else {}
    failed = failed_doc.get("trace_id")
    info["example_trace_ids"] = {"cache_hit": hit, "cache_miss": miss, "failed": failed}
    stg = lambda t: {s["stage"] for s in by.get(t, [])}  # noqa: E731
    look = lambda t: next((s for s in by.get(t, []) if s["stage"] == "cache_lookup"), None)  # noqa: E731
    record("part4_cache_hit_trace_has_a_hit_lookup_and_no_agent_stages", bool(hit) and look(hit) is not None and look(hit)["attrs"]["hit"] is True
           and not stg(hit) & {"planner", "writer", "reviewer"}, f"{hit}")
    need_miss = {"cache_lookup", "queue_wait_inbox", "planner", "queue_wait_tasks", "writer", "queue_wait_drafts", "reviewer", "queue_wait_final", "request"}
    record("part4_cache_miss_trace_covers_lookup_queues_planner_writer_reviewer", bool(miss) and look(miss) is not None and look(miss)["attrs"]["hit"] is False
           and need_miss <= stg(miss) and all(s["status"] == "ok" for s in by[miss]), f"{miss}")
    err = [s for s in by.get(failed, []) if s["status"] != "ok" and s["stage"] in ("planner", "writer", "reviewer")]
    record("part4_failed_trace_names_the_failing_stage_and_error", bool(failed) and bool(err) and bool(err[0]["error"]) and failed_doc.get("failing_stage") == err[0]["stage"],
           f"{failed}: stage {failed_doc.get('failing_stage')}, error {str(failed_doc.get('error'))[:80]}")
    bundles = {b["trace_id"]: b for b in jl(RAW / "bundles.jsonl") if not b.get("missing")}
    one = next((t for t in bundles if t in by), None)
    record("part4_one_trace_id_is_the_kafka_correlation_id_everywhere", bool(one) and all(m.get("correlation_id") == one for m in bundles[one]["messages"].values()),
           f"{one}: plan, draft and final messages carry the same id as the spans")
    # 4.3
    misses = [r for r in runs if r.get("phase") == "miss" and r.get("kind_result") == "confirmed_miss"]
    record("part4_50_confirmed_cache_misses", len(misses) >= 50 and len({r["trace_id"] for r in misses}) == len(misses), f"{len(misses)} confirmed misses")
    record("part4_every_confirmed_miss_was_not_served_from_the_cache",
           all((not r["is_cached"]) and r["similarity"] < THRESHOLD and r["status"] == "approved" and look(r["trace_id"]) is not None
               and look(r["trace_id"])["attrs"]["hit"] is False for r in misses) and bool(misses),
           f"similarity < {THRESHOLD}, is_cached false, cache_lookup span hit=false, status approved for all {len(misses)}")
    table_f, per_f = RAW / "latency_table.json", RAW / "latency_per_request.csv"
    if not table_f.exists() or not per_f.exists():
        record("part4_latency_table_recomputed_from_the_per_request_rows", False, "run python scripts/hw10_latency_report.py")
        return
    table = json.loads(table_f.read_text(encoding="utf-8"))
    rows = []
    for r in csv.DictReader(per_f.open(encoding="utf-8", newline="")):
        rows.append({k: (None if v == "" else (v if k == "trace_id" else float(v))) for k, v in r.items()})
    mine = {r["trace_id"] for r in misses}
    record("part4_latency_rows_are_exactly_the_confirmed_misses", {r["trace_id"] for r in rows} == mine and len(rows) >= 50, f"{len(rows)} per-request rows")
    re_t = {t["stage"]: t for t in summarize(rows)}
    same = all(abs(re_t[t["stage"]]["p50_ms"] - t["p50_ms"]) < 1e-6 and abs(re_t[t["stage"]]["p95_ms"] - t["p95_ms"]) < 1e-6 for t in table["misses"])
    record("part4_latency_table_recomputed_from_the_per_request_rows", same and len(re_t) == len(table["misses"]), f"{len(table['misses'])} rows match")
    want = {"Cache lookup", "Planner", "Writer", "Reviewer", "Queue wait (total)"}
    record("part4_table_has_p50_p95_for_every_required_stage_and_evaluation", want <= set(re_t) and any(k.startswith("Evaluation") for k in re_t)
           and all(re_t[k]["p50_ms"] <= re_t[k]["p95_ms"] for k in re_t), "; ".join(f"{k} {re_t[k]['p50_ms'] / 1000:.1f}/{re_t[k]['p95_ms'] / 1000:.1f}s" for k in re_t))
    path_share = sum(t["share_mean_pct"] for t in re_t.values() if not t["stage"].startswith(("Evaluation", "End-to-end")))
    record("part4_stage_shares_add_up_to_100_percent_of_the_miss_end_to_end", abs(path_share - 100) < 0.01, f"{path_share:.2f}%")
    hits = table.get("hits")
    record("part4_cache_hit_latency_reported_separately_and_lower", bool(hits) and hits["mean_ms"] < re_t["End-to-end (cache miss)"]["mean_ms"],
           f"hit mean {hits['mean_ms']:.0f} ms vs miss mean {re_t['End-to-end (cache miss)']['mean_ms'] / 1000:.1f} s" if hits else "no hit rows")
    info["dominant_stage"] = table.get("dominant")


def check_deliverables() -> None:
    missing = [f for f in ("RUN_LOG.txt", "METRICS.md", "AI_USE.md") if not (REPORT_DIR / f).exists()]
    record("required_deliverable_files_present", not missing, "missing: " + ", ".join(missing) if missing else "RUN_LOG.txt, METRICS.md, AI_USE.md, raw/")
    info["report_pdf_present"] = (REPORT_DIR / "Lourduraj_HW10.pdf").exists()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(REPORT_DIR / "verification.json"))
    ap.add_argument("--skip-suites", action="store_true", help="skip the offline test suites")
    args = ap.parse_args()
    code_before = tree_hash("code", "src", "dashboard")
    if not args.skip_suites:
        check_suites()
    check_part1()
    check_part2()
    check_part3()
    check_part4()
    check_deliverables()
    code_after = tree_hash("code", "src", "dashboard")
    record("verification_did_not_modify_application_code", code_before == code_after, f"sha256 of code/, src/ and dashboard/ before == after: {code_before[:12]}")
    passed = sum(1 for c in checks if c["passed"])
    info["suites_skipped"] = args.skip_suites
    result = {"homework_number": HOMEWORK_NUMBER, "sid4": SID4, "commit_hash": git("rev-parse", "HEAD") or "unknown", "model_configuration": MODEL_CONFIG,
              "seed": SEED, "verify_seed": VERIFY_SEED, "port_base": PORT_BASE, "generated_at": datetime.now(timezone.utc).isoformat(), "info": info,
              "checks_passed": passed, "checks_total": len(checks), "all_passed": passed == len(checks), "checks": checks}
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(checks)} checks passed.\nWrote {out}")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
