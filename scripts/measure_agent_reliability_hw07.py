"""HW7 Part 2 reliability measurement: N attempts (default 21) cycling the fixed tasks A, B, C with identical
settings; every attempt is saved (JSONL appended as it runs, so an interrupted run can be resumed).

   $env:MYSQL_PORT="43306"; python scripts\\measure_agent_reliability_hw07.py [--attempts 21] [--temperature 0.7] [--fresh]

Definitions (all computed from the saved per-attempt records):
  call-level well-formed rate   = (emitted tool calls - invalid tool calls) / emitted tool calls
  run clean before repair       = attempt with zero failure events (nothing needed the repair path)
  run OK after repair           = attempt that reached a final answer and in which every failure was repaired
  answer correct                = verifier (agent_tasks_hw07.verify) on the final answer
Failure classes: malformed_arguments, unknown_tool, text_instead_of_tool, lost_chain.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from agent_tasks_hw07 import REPO, STUDENT_BANNER, run_case  # noqa: E402

from src.agent_loop import FAILURE_CLASSES  # noqa: E402
from src.model_client import OllamaModelClient  # noqa: E402

RAW = REPO / "reports/hw07/raw"
ATTEMPTS = RAW / "agent_reliability_attempts.jsonl"
CSV_OUT = RAW / "agent_reliability_attempts.csv"
SUMMARY = RAW / "agent_reliability_summary.json"
CYCLE = ["A", "B", "C"]


def pct(a: int, b: int) -> str:
    return f"{100.0 * a / b:5.1f}%" if b else "  n/a"


def summarize(rows: list) -> dict:
    n = len(rows)
    emitted = sum(r["emitted_calls"] for r in rows)
    invalid = sum(r["invalid_calls"] for r in rows)
    classes = Counter(e["class"] for r in rows for e in r["events"])
    repaired = Counter(e["class"] for r in rows for e in r["events"] if e["repaired"])
    clean = sum(1 for r in rows if not r["events"])
    ok_after = sum(1 for r in rows if r["stop_reason"] == "final_answer" and all(e["repaired"] for e in r["events"]))
    correct = sum(1 for r in rows if r["answer_correct"])
    by_task = {}
    for t in sorted({r["case_id"] for r in rows}):
        sub = [r for r in rows if r["case_id"] == t]
        by_task[t] = {"attempts": len(sub), "correct": sum(1 for r in sub if r["answer_correct"]),
                      "clean_first_try": sum(1 for r in sub if not r["events"])}
    return {
        "attempts": n, "emitted_calls": emitted, "invalid_calls": invalid,
        "call_well_formed_rate": (emitted - invalid) / emitted if emitted else None,
        "runs_clean_before_repair": clean, "runs_ok_after_repair": ok_after, "answers_correct": correct,
        "failure_events": dict(classes), "failure_events_repaired": dict(repaired),
        "stop_reasons": dict(Counter(r["stop_reason"] for r in rows)),
        "mean_tool_calls": sum(r["total_tool_calls"] for r in rows) / n if n else None,
        "mean_wall_s": sum(r["wall_ms"] for r in rows) / n / 1000 if n else None,
        "total_tokens": sum(r["input_tokens"] + r["output_tokens"] for r in rows),
        "by_task": by_task,
    }


def print_summary(s: dict, temperature: float, model: str) -> None:
    n = s["attempts"]
    print("\n" + "=" * 78)
    print(f"RELIABILITY SUMMARY  model={model} temperature={temperature} attempts={n}")
    print(f"call-level well-formed rate : {s['emitted_calls'] - s['invalid_calls']}/{s['emitted_calls']} "
          f"= {pct(s['emitted_calls'] - s['invalid_calls'], s['emitted_calls'])}")
    print(f"runs clean BEFORE repair    : {s['runs_clean_before_repair']}/{n} = {pct(s['runs_clean_before_repair'], n)}")
    print(f"runs OK AFTER repair        : {s['runs_ok_after_repair']}/{n} = {pct(s['runs_ok_after_repair'], n)}")
    print(f"answers correct (verifier)  : {s['answers_correct']}/{n} = {pct(s['answers_correct'], n)}")
    print(f"{'failure class':<24}{'events':<9}{'repaired':<9}")
    for c in FAILURE_CLASSES:
        print(f"{c:<24}{s['failure_events'].get(c, 0):<9}{s['failure_events_repaired'].get(c, 0):<9}")
    print(f"stop reasons: {s['stop_reasons']}")
    print(f"mean tool calls/attempt {s['mean_tool_calls']:.2f}  mean wall {s['mean_wall_s']:.1f}s  tokens {s['total_tokens']}")
    for t, v in s["by_task"].items():
        print(f"  task {t}: correct {v['correct']}/{v['attempts']}  clean first try {v['clean_first_try']}/{v['attempts']}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--attempts", type=int, default=21)
    ap.add_argument("--temperature", type=float, default=0.7)
    ap.add_argument("--fresh", action="store_true", help="delete earlier attempts and start over")
    ap.add_argument("--summary-only", action="store_true")
    args = ap.parse_args()
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    RAW.mkdir(parents=True, exist_ok=True)
    if args.fresh and ATTEMPTS.exists():
        ATTEMPTS.unlink()
    done = [json.loads(line) for line in ATTEMPTS.read_text(encoding="utf-8").splitlines()] if ATTEMPTS.exists() else []

    client = OllamaModelClient()
    print(STUDENT_BANNER)
    if not args.summary_only:
        client.check_connection()
        print(f"model={client.model} temperature={args.temperature}; {len(done)} attempts already saved, target {args.attempts}")
        for i in range(len(done) + 1, args.attempts + 1):
            tid = CYCLE[(i - 1) % len(CYCLE)]
            rec = run_case(tid, client=client, temperature=args.temperature, log=None)
            rec["attempt"] = i
            with ATTEMPTS.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            done.append(rec)
            flags = ",".join(f"{e['class']}{'(fixed)' if e['repaired'] else '(NOT fixed)'}" for e in rec["events"]) or "-"
            print(f"attempt {i:>2}/{args.attempts} task {tid} calls={rec['total_tool_calls']} invalid={rec['invalid_calls']} "
                  f"stop={rec['stop_reason']} correct={rec['answer_correct']} events={flags} {rec['wall_ms'] / 1000:.1f}s")

    if not done:
        print("no attempts saved yet")
        return 1
    temp = done[0].get("temperature", args.temperature)
    summary = summarize(done)
    summary.update({"model": done[0].get("model"), "temperature": temp})
    SUMMARY.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    with CSV_OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["attempt", "task", "stop_reason", "answer_correct", "tool_calls", "emitted_calls", "invalid_calls",
                    "repair_reprompts", "failure_classes", "all_repaired", "input_tokens", "output_tokens", "wall_ms"])
        for r in done:
            w.writerow([r["attempt"], r["case_id"], r["stop_reason"], r["answer_correct"], r["total_tool_calls"],
                        r["emitted_calls"], r["invalid_calls"], r["repair_reprompts"],
                        "|".join(e["class"] for e in r["events"]), all(e["repaired"] for e in r["events"]),
                        r["input_tokens"], r["output_tokens"], r["wall_ms"]])
    print_summary(summary, temp, summary["model"])
    print(f"\nsaved: {ATTEMPTS.relative_to(REPO)}, {CSV_OUT.relative_to(REPO)}, {SUMMARY.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
