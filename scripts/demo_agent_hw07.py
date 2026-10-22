"""HW7 Part 2 demo: run fixed tasks A, B, C and the error-recovery case D through run_agent on the live
Ollama model, print each tool call and the totals, and save the raw records.

   $env:MYSQL_PORT="43306"; python scripts\\demo_agent_hw07.py [--tasks A B C D] [--save]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from agent_tasks_hw07 import REPO, STUDENT_BANNER, TASKS, run_case  # noqa: E402

from src.model_client import OllamaModelClient  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", nargs="+", default=["A", "B", "C", "D"], choices=list(TASKS))
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--save", action="store_true", help="write reports/hw07/raw/agent_tasks.jsonl")
    ap.add_argument("--append", action="store_true", help="with --save: keep earlier records instead of starting the file fresh")
    args = ap.parse_args()
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    client = OllamaModelClient()
    client.check_connection()
    out = REPO / "reports/hw07/raw/agent_tasks.jsonl"
    if args.save and not args.append and out.exists():
        out.unlink()
    print(STUDENT_BANNER)
    print(f"model={client.model} temperature={args.temperature}\n")
    results = []
    for tid in args.tasks:
        spec = TASKS[tid]
        print("=" * 78)
        print(f"TASK {tid}: {spec['title']}")
        print(f"prompt: {spec['prompt']}")
        rec = run_case(tid, client=client, temperature=args.temperature)
        if args.save:  # written AFTER verification so the saved record carries expected/answer_correct
            out.parent.mkdir(parents=True, exist_ok=True)
            with out.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(f"final answer: {rec['final_text']}")
        print(f"verifier: {'PASS' if rec['answer_correct'] else 'FAIL'} {rec['verifier_problems'] or ''}")
        print(f"expected: {json.dumps(rec['expected'], ensure_ascii=False)}\n")
        results.append(rec)

    print("=" * 78)
    print(f"{'task':<5}{'tool calls':<12}{'invalid':<9}{'reprompts':<11}{'stop':<14}{'tokens':<10}{'wall s':<8}answer")
    for r in results:
        print(f"{r['case_id']:<5}{r['total_tool_calls']:<12}{r['invalid_calls']:<9}{r['repair_reprompts']:<11}"
              f"{r['stop_reason']:<14}{r['input_tokens'] + r['output_tokens']:<10}{r['wall_ms'] / 1000:<8.1f}"
              f"{'correct' if r['answer_correct'] else 'WRONG'}")
    if args.save:
        print(f"\nraw records appended to {out.relative_to(REPO)}")
    return 0 if all(r["answer_correct"] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
