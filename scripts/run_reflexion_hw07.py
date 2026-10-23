"""HW7 Part 3 runner: Reflexion vs the original Part 2 agent on the same fixed tasks A, B, C.

  python scripts\\run_reflexion_hw07.py --arm reflexion --attempts 21     # Part 2 loop + verifier + Reflexion
  python scripts\\run_reflexion_hw07.py --arm ablation  --attempts 12     # same, but the loop's step-count repair is OFF
  python scripts\\run_reflexion_hw07.py --score-original                  # re-score the saved Part 2 runs (no model)
  python scripts\\run_reflexion_hw07.py --compare [--show-reflections]    # table from the saved raw data (no model)

All arms use qwen3:8b, temperature 0.7 (same settings as the Part 2 reliability run), the same prompts and the same
verifier. Runs are appended to reports/hw07/raw/ as they finish, so an interrupted run resumes with the same command.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from statistics import mean

sys.path.insert(0, str(Path(__file__).resolve().parent))
from agent_tasks_hw07 import REPO, STUDENT_BANNER, TASKS, expected_for  # noqa: E402
from reflexion_tasks_hw07 import verify_task  # noqa: E402

RAW = REPO / "reports/hw07/raw"
FILES = {"reflexion": RAW / "reflexion_attempts.jsonl", "ablation": RAW / "reflexion_ablation_attempts.jsonl",
         "original": RAW / "reflexion_original_scored.jsonl"}
PART2_RUNS = RAW / "agent_reliability_attempts.jsonl"
COMPARISON_JSON = RAW / "reflexion_comparison.json"
COMPARISON_MD = RAW / "reflexion_comparison.md"
CYCLE = ["A", "B", "C"]


def attempt_summary(att: dict) -> dict:
    rec, v = att["record"], att["verdict"]
    return {"attempt": att["attempt"], "ok": v["ok"], "content_ok": v["content_ok"], "process_ok": v["process_ok"],
            "unsupported": v["unsupported_claims"], "rules": [p["rule"] for p in v["problems"]],
            "tool_calls": rec["total_tool_calls"], "tokens": rec["input_tokens"] + rec["output_tokens"],
            "wall_ms": rec["wall_ms"], "stop_reason": rec["stop_reason"]}


def row_from_reflexion(rec: dict, arm: str, idx: int, task: str, temperature: float) -> dict:
    atts = [attempt_summary(a) for a in rec["attempts"]]
    return {"arm": arm, "n": idx, "task": task, "temperature": temperature, "success": rec["success"],
            "stop_reason": rec["stop_reason"], "retries": rec["retries"], "attempts": atts,
            "reflections": len(rec["reflections"]), "total_tool_calls": rec["total_tool_calls"],
            "total_tokens": rec["total_tokens"], "latency_ms": rec["wall_ms"],
            "final_unsupported": atts[-1]["unsupported"] if atts else [],
            "false_rejections": sum(1 for a in atts if not a["ok"] and a["content_ok"])}


def row_from_part2(rec: dict, verdict: dict, idx: int) -> dict:
    a = {"attempt": 1, "ok": verdict["ok"], "content_ok": verdict["content_ok"], "process_ok": verdict["process_ok"],
         "unsupported": verdict["unsupported_claims"], "rules": [p["rule"] for p in verdict["problems"]],
         "tool_calls": rec["total_tool_calls"], "tokens": rec["input_tokens"] + rec["output_tokens"],
         "wall_ms": rec["wall_ms"], "stop_reason": rec["stop_reason"]}
    return {"arm": "original", "n": idx, "task": rec["case_id"], "temperature": rec.get("temperature"),
            "success": verdict["ok"], "stop_reason": "success" if verdict["ok"] else "rejected", "retries": 0,
            "attempts": [a], "reflections": 0, "total_tool_calls": a["tool_calls"], "total_tokens": a["tokens"],
            "latency_ms": a["wall_ms"], "final_unsupported": a["unsupported"],
            "false_rejections": int(not a["ok"] and a["content_ok"])}


def first_attempt_view(row: dict) -> dict:
    """The same run seen as if only its first attempt existed (no Reflexion)."""
    a = row["attempts"][0]
    return {**row, "success": a["ok"], "retries": 0, "reflections": 0, "total_tool_calls": a["tool_calls"],
            "total_tokens": a["tokens"], "latency_ms": a["wall_ms"], "final_unsupported": a["unsupported"],
            "false_rejections": int(not a["ok"] and a["content_ok"]), "stop_reason": "success" if a["ok"] else "rejected"}


def summarize(rows: list) -> dict:
    n = len(rows)
    if not n:
        return {"n": 0}
    return {
        "n": n,
        "task_success": sum(1 for r in rows if r["success"]),
        "unsupported_claims_total": sum(len(r["final_unsupported"]) for r in rows),
        "runs_with_unsupported": sum(1 for r in rows if r["final_unsupported"]),
        "runs_with_retry": sum(1 for r in rows if r["retries"] > 0),
        "mean_retries": mean(r["retries"] for r in rows),
        "mean_tool_calls": mean(r["total_tool_calls"] for r in rows),
        "mean_tokens": mean(r["total_tokens"] for r in rows),
        "mean_latency_ms": mean(r["latency_ms"] for r in rows),
        "false_rejections": sum(r["false_rejections"] for r in rows),
        "stop_reasons": {k: sum(1 for r in rows if r["stop_reason"] == k) for k in sorted({r["stop_reason"] for r in rows})},
        "by_task": {t: {"n": sum(1 for r in rows if r["task"] == t), "success": sum(1 for r in rows if r["task"] == t and r["success"]),
                        "runs_with_retry": sum(1 for r in rows if r["task"] == t and r["retries"] > 0)}
                    for t in sorted({r["task"] for r in rows})},
    }


def load(path: Path) -> list:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()] if path.exists() else []


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO))
    except ValueError:
        return str(path)


def pct(a, b):
    return f"{a}/{b} ({100.0 * a / b:.1f}%)" if b else "n/a"


def comparison(rows_by_arm: dict) -> dict:
    cols = {
        "Original (Part 2 as built)": rows_by_arm["original"],
        "Reflexion (Part 2 loop + verifier + reflections)": rows_by_arm["reflexion"],
        "Ablation, 1st attempt only (no step-repair, no Reflexion)": [first_attempt_view(r) for r in rows_by_arm["ablation"]],
        "Ablation with Reflexion (no step-repair)": rows_by_arm["ablation"],
    }
    return {name: summarize(rows) for name, rows in cols.items()}


def render_table(comp: dict) -> str:
    names = list(comp)
    lines = ["| Metric | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]

    def row(label, fn):
        lines.append(f"| {label} | " + " | ".join(fn(comp[n]) if comp[n]["n"] else "n/a" for n in names) + " |")

    row("Runs", lambda s: str(s["n"]))
    row("Task success (verifier accepts)", lambda s: pct(s["task_success"], s["n"]))
    row("Unsupported claims in final answers", lambda s: f"{s['unsupported_claims_total']} (in {s['runs_with_unsupported']} runs)")
    row("Retry rate (runs with >=1 retry)", lambda s: pct(s["runs_with_retry"], s["n"]))
    row("Mean retries per run", lambda s: f"{s['mean_retries']:.2f}")
    row("Mean tool calls per run", lambda s: f"{s['mean_tool_calls']:.2f}")
    row("Mean tokens per run", lambda s: f"{s['mean_tokens']:.0f}")
    row("Mean latency per run (ms)", lambda s: f"{s['mean_latency_ms']:.0f}")
    row("Verifier false rejections", lambda s: str(s["false_rejections"]))
    row("Stop reasons", lambda s: ", ".join(f"{k}: {v}" for k, v in s["stop_reasons"].items()))
    return "\n".join(lines)


def show_reflections(rows: list, label: str) -> None:
    shown = 0
    for r in rows:
        if r.get("reflections_data"):
            for refl in r["reflections_data"]:
                shown += 1
                ev = refl["evidence"]
                print(f"\n[{label}] run {r['n']} task {r['task']}: reflection after attempt {refl['after_attempt']} (source: {refl['source']})")
                print(f"  evidence - verifier rule : {ev['verifier_rule']}")
                print(f"  evidence - verifier says : {'; '.join(ev['verifier_detail'])}")
                print(f"  evidence - tool calls    : {[(c['tool'], c['arguments']) for c in ev['tool_calls']]}")
                print(f"  evidence - observation   : {ev['last_observation']}")
                print(f"  evidence - final answer  : {ev['final_answer']}")
                print(f"  reflection - failure     : {refl['failure']}")
                print(f"  reflection - strategy    : {refl['strategy']}")
                print(f"  outcome: run ended {r['stop_reason']} after {len(r['attempts'])} attempt(s)")
    if not shown:
        print(f"[{label}] no reflections stored (no attempt was rejected)")


def do_compare(show: bool) -> int:
    rows_by_arm = {arm: [r["row"] for r in load(path)] for arm, path in FILES.items()}
    if show:
        for arm in ("reflexion", "ablation"):
            full = [{**r["row"], "reflections_data": r["reflexion"]["reflections"]} for r in load(FILES[arm])]
            show_reflections(full, arm)
    comp = comparison(rows_by_arm)
    print("\n" + "=" * 78)
    print("REFLEXION vs ORIGINAL - qwen3:8b, temperature 0.7, tasks A/B/C")
    table = render_table(comp)
    print(table)
    for name, stats in comp.items():
        by = stats.get("by_task", {})
        print(f"{name} - by task: " + ", ".join(f"{t}: success {v['success']}/{v['n']}, runs with retry {v['runs_with_retry']}" for t, v in by.items()))
    fr = [(a, r["n"], r["task"], att["attempt"], att["rules"]) for a, rows in rows_by_arm.items() for r in rows
          for att in r["attempts"] if not att["ok"] and att["content_ok"]]
    print(f"\nattempts rejected although the answer content was correct and supported (rule failed): {len(fr)}")
    for a, n, t, k, rules in fr[:12]:
        print(f"  arm {a} run {n} task {t} attempt {k}: rules {rules}")
    COMPARISON_JSON.write_text(json.dumps(comp, indent=2), encoding="utf-8")
    COMPARISON_MD.write_text(table + "\n", encoding="utf-8")
    print(f"\nsaved {rel(COMPARISON_JSON)} and {rel(COMPARISON_MD)}")
    return 0


def do_score_original() -> int:
    print(STUDENT_BANNER)
    recs = load(PART2_RUNS)
    if not recs:
        print(f"{PART2_RUNS} not found")
        return 1
    expected = {t: expected_for(t) for t in CYCLE}
    out = FILES["original"]
    with out.open("w", encoding="utf-8") as fh:
        for rec in recs:
            verdict = verify_task(rec["case_id"], rec, expected[rec["case_id"]])
            row = row_from_part2(rec, verdict, rec["attempt"])
            fh.write(json.dumps({"row": row, "verdict": verdict, "source_run_id": rec["run_id"], "case_id": rec["case_id"]}, ensure_ascii=False) + "\n")
            print(f"part2 attempt {rec['attempt']:>2} task {rec['case_id']}: {'ACCEPT' if verdict['ok'] else 'REJECT'} "
                  f"{[p['rule'] for p in verdict['problems']] or ''} unsupported={verdict['unsupported_claims']}")
    print(f"scored {len(recs)} saved Part 2 runs (no model call) -> {rel(out)}")
    return 0


def do_run(arm: str, attempts: int, temperature: float, fresh: bool) -> int:
    from src.agent_loop import default_recall_execute  # noqa: PLC0415
    from src.model_client import OllamaModelClient  # noqa: PLC0415
    from src.reflexion import run_reflexion  # noqa: PLC0415

    path = FILES[arm]
    RAW.mkdir(parents=True, exist_ok=True)
    if fresh and path.exists():
        path.unlink()
    done = load(path)
    client = OllamaModelClient()
    client.check_connection()
    print(STUDENT_BANNER)
    print(f"arm={arm} model={client.model} temperature={temperature}; {len(done)} runs already saved, target {attempts}")
    expected = {t: expected_for(t) for t in CYCLE}
    execute = default_recall_execute()
    for i in range(len(done) + 1, attempts + 1):
        tid = CYCLE[(i - 1) % len(CYCLE)]
        spec = TASKS[tid]
        print(f"\n--- run {i}/{attempts} task {tid}: {spec['title']}")
        rec = run_reflexion(
            spec["prompt"], client=client, execute=execute,
            verifier=lambda r, tid=tid: verify_task(tid, r, expected[tid]),
            min_tool_calls=spec["min_tool_calls"] if arm == "reflexion" else 0,
            temperature=temperature, case_id=tid, scope=f"student-9619/run-{i}",
            log=print)
        row = row_from_reflexion(rec, arm, i, tid, temperature)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"row": row, "reflexion": rec, "case_id": tid}, ensure_ascii=False) + "\n")
        print(f"run {i:>2} task {tid}: stop={rec['stop_reason']} attempts={rec['attempts_used']} tool_calls={rec['total_tool_calls']} "
              f"tokens={rec['total_tokens']} {rec['wall_ms'] / 1000:.1f}s false_rejections={row['false_rejections']}")
    rows = [r["row"] for r in load(path)]
    s = summarize(rows)
    print("\n" + "=" * 78)
    print(f"{arm.upper()} SUMMARY ({s['n']} runs): success {pct(s['task_success'], s['n'])}, runs with retry {s['runs_with_retry']}, "
          f"stop reasons {s['stop_reasons']}, mean tool calls {s['mean_tool_calls']:.2f}, mean tokens {s['mean_tokens']:.0f}, "
          f"mean latency {s['mean_latency_ms'] / 1000:.1f}s")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", choices=["reflexion", "ablation"])
    ap.add_argument("--attempts", type=int, default=21)
    ap.add_argument("--temperature", type=float, default=0.7)
    ap.add_argument("--fresh", action="store_true")
    ap.add_argument("--score-original", action="store_true")
    ap.add_argument("--compare", action="store_true")
    ap.add_argument("--show-reflections", action="store_true")
    args = ap.parse_args()
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    if args.score_original:
        return do_score_original()
    if args.compare:
        print(STUDENT_BANNER)
        return do_compare(args.show_reflections)
    if args.arm:
        return do_run(args.arm, args.attempts, args.temperature, args.fresh)
    ap.error("choose --arm, --score-original or --compare")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
