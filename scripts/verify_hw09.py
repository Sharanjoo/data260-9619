"""HW9 self-check (make verify-hw09): live smoke checks of Redis plus the saved evidence for every part.

Live checks (need `docker compose up -d`: redis-stack and mysql):
  Redis answers PING and has the vector index, test_hw9_part1.py (Redis counter, DB sync every 10th increment), and
  hw9_cache_smoke.py (embed, store, hit/miss against the real index).
Offline checks: test_hw9_cache.py, test_hw9_sweep.py, test_hw9_part4.py (a scripted model stands in for qwen3:1.7b, so no Ollama).
Saved evidence: Part 2 summary, Part 3 sweep / false hit / cost / stale demo, Part 4 training, gate, variants and demo, the
data files (questions only, no answers), the lessons file fields, and the deliverable files. The cache cases file must have been
committed before the sweep output was written. It does NOT modify application code: it hashes code/ before and after.

Usage (repo root):   python scripts/verify_hw09.py            (writes reports/hw09/verification.json)
                     python scripts/verify_hw09.py --skip-live
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REPORT_DIR = REPO_ROOT / "reports" / "hw09"
RAW = REPORT_DIR / "raw"
DATA = REPO_ROOT / "data" / "hw09"
sys.path.insert(0, str(REPO_ROOT / "code"))

from cache_layer.config import CACHE_INDEX, PORT_BASE, REDIS_HOST, REDIS_PORT, SEED, SID4, VERIFY_SEED  # noqa: E402

HOMEWORK_NUMBER = 9
THRESHOLDS = ["0.75", "0.8", "0.85", "0.9", "0.95"]
MODEL_CONFIG = ("Parts 2-3: HW8 pipeline (Planner, Writer, Reviewer) with qwen3:8b via Ollama, cache = Redis Stack vector index "
                "(FLAT, COSINE, 384 dims) with all-MiniLM-L6-v2 embeddings, default threshold 0.85, shipped threshold 0.95. "
                "Part 4: Answering Agent = qwen3:1.7b via Ollama (temperature 0, seed 9619), Evaluator = rule-based against "
                "reference_dataset.json; qwen3:8b answered all 16 first training questions correctly, so it left nothing to learn from")
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


def load(name: str):
    path = RAW / name
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def run_script(label: str, script: str, timeout: int = 900, need: str = "") -> None:
    try:
        p = subprocess.run([sys.executable, str(REPO_ROOT / "scripts" / script)], cwd=REPO_ROOT, capture_output=True, text=True, timeout=timeout)
        lines = [ln for ln in p.stdout.strip().splitlines() if ln.strip()]
        last = lines[-1] if lines else (p.stderr.strip().splitlines() or ["no output"])[-1]
        record(label, p.returncode == 0 and (need in last if need else True), last[:160])
    except Exception as exc:  # noqa: BLE001
        record(label, False, f"{type(exc).__name__}: {exc}")


# ---------------------------------------------------------------- live
def check_redis() -> None:
    try:
        import redis  # noqa: PLC0415

        r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, socket_timeout=5)
        record("redis_answers_ping", r.ping() is True, f"{REDIS_HOST}:{REDIS_PORT}")
        try:
            n = r.ft(CACHE_INDEX).info().get("num_docs")
            record("redis_vector_index_exists", True, f"{CACHE_INDEX}, {n} documents")
        except Exception as exc:  # noqa: BLE001
            record("redis_vector_index_exists", False, f"{type(exc).__name__}: {exc} (run hw9_cache_smoke.py once)")
    except Exception as exc:  # noqa: BLE001
        record("redis_answers_ping", False, f"{type(exc).__name__}: {exc} (docker compose up -d)")
    run_script("part1_counter_suite_passes_on_real_redis", "test_hw9_part1.py")
    run_script("part2_cache_smoke_passes_on_real_redis", "hw9_cache_smoke.py", need="PASS")


# ---------------------------------------------------------------- offline
def check_suites() -> None:
    for script in ("test_hw9_cache.py", "test_hw9_sweep.py", "test_hw9_part4.py"):
        run_script(f"suite_{script[:-3]}", script)


def check_part2() -> None:
    s = load("part2_summary.json")
    if s is None:
        record("part2_summary_saved", False, "raw/part2_summary.json (python scripts/hw9_part2_run.py)")
        return
    record("part2_at_least_10_queries_all_behaved_as_intended", s["queries"] >= 10 and s["met_expectation"] == s["queries"],
           f"{s['met_expectation']}/{s['queries']} behaved as intended")
    record("part2_hit_rate_and_latencies_recorded", s["cache_hits"] == round(s["hit_rate_percent"] * s["queries"] / 100)
           and s["mean_latency_ms_cached"] < s["mean_latency_ms_not_cached"],
           f"hit rate {s['hit_rate_percent']}%, cached {s['mean_latency_ms_cached']} ms, not cached {s['mean_latency_ms_not_cached']} ms")


def check_part3() -> None:
    yaml_rel = "data/hw09/cache_cases.yaml"
    committed = git("log", "-1", "--format=%ct", "--", yaml_rel)
    clean = git("status", "--porcelain", "--", yaml_rel) == ""
    sweep = RAW / "part3_sweep.json"
    ok = bool(committed) and clean and sweep.exists() and int(committed) < sweep.stat().st_mtime
    record("part3_cases_committed_before_the_sweep_and_unchanged", ok,
           f"cache_cases.yaml commit {git('log', '-1', '--format=%h', '--', yaml_rel)}, working copy clean={clean}")
    sw = load("part3_sweep.json")
    if sw is None:
        record("part3_sweep_saved", False, "raw/part3_sweep.json (python scripts/hw9_part3_sweep.py)")
        return
    sums = sw["summaries"]
    hits = [sums[t]["hit_rate"] for t in THRESHOLDS]
    fh = [sums[t]["false_hits"] for t in THRESHOLDS]
    record("part3_sweep_covers_five_thresholds_on_40_cases", sw["thresholds"] == [float(t) for t in THRESHOLDS]
           and all(sums[t]["cases"] == 40 for t in THRESHOLDS), "0.75 0.80 0.85 0.90 0.95")
    record("part3_hit_rate_and_false_hits_fall_as_the_threshold_rises", hits == sorted(hits, reverse=True) and fh == sorted(fh, reverse=True),
           f"hit rate {hits}; false hits {fh}")
    fhit = load("part3_false_hit.json")
    record("part3_one_false_hit_shown_in_full", bool(fhit) and fhit["cached_query"] != fhit["incoming_query"]
           and fhit["cached_answer"] != fhit["correct_answer"] and fhit["similarity"] >= fhit["threshold"],
           f"{fhit['case']} similarity {fhit['similarity']} at threshold {fhit['threshold']}" if fhit else "raw/part3_false_hit.json missing")
    cost = load("part3_cost.json")
    if cost is None:
        record("part3_cost_model_saved", False, "raw/part3_cost.json")
    else:
        totals = {t: cost["costs"][t]["total_cost"] for t in THRESHOLDS}
        best = min(totals, key=totals.get)
        recomputed = all(abs(cost["costs"][t]["total_cost"] - (cost["costs"][t]["not_served"] * cost["c_miss"]
                                                                + cost["costs"][t]["false_hits"] * cost["c_false"])) < 0.01 for t in THRESHOLDS)
        record("part3_cost_model_recomputes_and_picks_the_cheapest_threshold", recomputed and cost["chosen_by_lowest_total"] == best,
               f"c_miss ${cost['c_miss']}, c_false ${cost['c_false']}, cheapest {best}")
    st = load("part3_stale.json")
    if st is None:
        record("part3_stale_answer_demo_saved", False, "raw/part3_stale.json (python scripts/hw9_part3_stale.py)")
    else:
        record("part3_stale_answer_served_then_invalidated_then_fresh", all(st["checks"].values()) and st["3_stale_hit"]["has_old_value"]
               and st["4_with_check"]["stale_entry_removed"] and st["5_after_refresh"]["has_new_value"],
               f"old {st['old_units']} -> new {st['new_units']}; version check adds "
               f"{round(st['6_cost_of_check']['mean_ms_with_check'] - st['6_cost_of_check']['mean_ms_without_check'], 1)} ms per hit")


def check_part4() -> None:
    for name in ("training", "validation", "test"):
        path = DATA / f"{name}_data.json"
        items = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
        record(f"part4_{name}_data_has_questions_only", bool(items) and all(set(q) == {"id", "question"} for q in items), f"{len(items)} questions")
    lessons_path = DATA / "lessons.json"
    lessons = json.loads(lessons_path.read_text(encoding="utf-8"))["lessons"] if lessons_path.exists() else None
    fields = {"lesson_id", "failure_pattern", "correction", "created_at", "use_count"}
    record("part4_lessons_json_has_the_required_fields", lessons is not None and bool(lessons) and all(fields <= set(x) for x in lessons),
           f"{len(lessons or [])} lessons: " + ", ".join(f"{x['lesson_id']}={x['failure_pattern']}" for x in lessons or []))
    gate = load("part4_gate.json")
    record("part4_gate_accepted_lessons_match_lessons_json", bool(gate) and lessons is not None
           and sorted(gate["accepted"]) == sorted(x["lesson_id"] for x in lessons),
           f"rule={gate['rule']}, accepted {gate['accepted']}" if gate else "raw/part4_gate.json missing")
    var = load("part4_variants.json")
    if var is None:
        record("part4_four_variants_saved", False, "raw/part4_variants.json")
    else:
        record("part4_four_variants_on_20_test_questions", sorted(var) == ["V1", "V2", "V3", "V4"] and all(v["n"] == 20 for v in var.values()),
               "; ".join(f"{k} {v['first_pass']}/20 -> {v['final_pass']}/20" for k, v in var.items()))
        record("part4_lessons_plus_retry_is_not_worse_than_baseline", var["V4"]["final_pass"] >= var["V1"]["final_pass"],
               f"V4 {var['V4']['final_pass']}/20 vs V1 {var['V1']['final_pass']}/20")
        attempts = [json.loads(ln)["n_attempts"] for k in ("V1", "V2", "V3", "V4") for ln in
                    (RAW / f"part4_variant_{k}.jsonl").read_text(encoding="utf-8").splitlines() if ln.strip()]
        record("part4_never_more_than_two_attempts", bool(attempts) and max(attempts) <= 2, f"max attempts {max(attempts) if attempts else 'n/a'}")
    demo = load("part4_demo.json")
    ok = bool(demo) and demo["no_retry"]["attempts"][0]["forced"] and not demo["no_retry"]["passed_final"] \
        and demo["with_retry"]["n_attempts"] == 2 and demo["with_retry"]["passed_final"]
    record("part4_controlled_bad_first_answer_is_caught_and_fixed_on_retry", ok,
           "forced stale answer fails without retry, passes on attempt 2" if ok else "raw/part4_demo.json missing or unexpected")


def check_deliverables() -> None:
    missing = [f for f in ("RUN_LOG.txt", "METRICS.md", "AI_USE.md") if not (REPORT_DIR / f).exists()]
    record("required_deliverable_files_present", not missing, "missing: " + ", ".join(missing) if missing else "RUN_LOG.txt, METRICS.md, AI_USE.md, raw/")
    info["report_pdf_present"] = (REPORT_DIR / "Lourduraj_HW9.pdf").exists()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(REPORT_DIR / "verification.json"))
    ap.add_argument("--skip-live", action="store_true", help="skip the checks that need docker compose / Redis")
    args = ap.parse_args()
    code_before = tree_hash("code", "src")
    if not args.skip_live:
        check_redis()
    check_suites()
    check_part2()
    check_part3()
    check_part4()
    check_deliverables()
    code_after = tree_hash("code", "src")
    record("verification_did_not_modify_application_code", code_before == code_after, f"sha256 of code/ and src/ before == after: {code_before[:12]}")

    passed = sum(1 for c in checks if c["passed"])
    info.update({"redis_image": "redis/redis-stack-server:7.4.0-v3", "redis_host_port": REDIS_PORT, "live_checks_skipped": args.skip_live})
    result = {
        "homework_number": HOMEWORK_NUMBER, "sid4": SID4, "commit_hash": git("rev-parse", "HEAD") or "unknown",
        "model_configuration": MODEL_CONFIG, "seed": SEED, "verify_seed": VERIFY_SEED, "port_base": PORT_BASE,
        "generated_at": datetime.now(timezone.utc).isoformat(), "info": info, "checks_passed": passed, "checks_total": len(checks),
        "all_passed": passed == len(checks), "checks": checks,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(checks)} checks passed.\nWrote {out}")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
