"""Homework 2 Part 4 #4: compare turn ceilings of 2 vs 10, 20 runs each, same frozen input."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = Path(__file__).resolve().parent
for p in (PROJECT_ROOT, SCRIPTS_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from src.model_client import ModelClientError
from run_schema_experiment import run_once


def run_batch(ceiling: int, runs: int, title: str, content: str, email: str,
              model: str, base_url: str, output_path: Path, resume: bool) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    if resume and output_path.exists():
        existing = json.loads(output_path.read_text(encoding="utf-8"))
        results = existing.get("runs", [])
        print(f"Resuming ceiling={ceiling}: {len(results)} runs already recorded.")

    while len(results) < runs:
        run_index = len(results) + 1
        print(f"\n=== ceiling={ceiling} run {run_index}/{runs} ===")
        try:
            result = run_once(title, content, email, model, base_url, ceiling)
        except ModelClientError as exc:
            print(f"ERROR on ceiling={ceiling} run {run_index}: {exc}", file=sys.stderr)
            raise
        print(json.dumps(
            {k: v for k, v in result.items() if k not in ("final_planner_proposal", "final_reviewer_feedback")},
            indent=2,
        ))
        results.append(result)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps({"turn_ceiling": ceiling, "model": model, "runs": results}, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    return results


def summarize(label: str, results: List[Dict[str, Any]]) -> Dict[str, Any]:
    completed = [r for r in results if not r["abandoned"]]
    completion_rate = round(len(completed) / len(results), 4) if results else 0.0
    mean_latency = round(sum(r["latency_ms"] for r in results) / len(results), 3) if results else None
    print(f"\n=== {label} (n={len(results)}) ===")
    print(f"completion_rate: {completion_rate}")
    print(f"mean_latency_ms: {mean_latency}")
    return {"completion_rate": completion_rate, "mean_latency_ms": mean_latency, "n": len(results)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-file", type=Path, default=Path("reports/hw02/cases/schema_input.json"))
    parser.add_argument("--runs-per-ceiling", type=int, default=20)
    parser.add_argument("--model", default="qwen3:8b")
    parser.add_argument("--base-url", default="http://localhost:11434")
    parser.add_argument("--output-dir", type=Path, default=Path("reports/hw02/raw"))
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    data = json.loads(args.input_file.read_text(encoding="utf-8"))
    title, content, email = data["title"], data["content"], data.get("email", "")

    summary: Dict[str, Any] = {}
    try:
        for ceiling in (2, 10):
            output_path = args.output_dir / f"ceiling_comparison_ceiling{ceiling}.json"
            results = run_batch(ceiling, args.runs_per_ceiling, title, content, email,
                                 args.model, args.base_url, output_path, args.resume)
            summary[f"ceiling_{ceiling}"] = summarize(f"ceiling={ceiling}", results)
    except KeyboardInterrupt:
        print("\nInterrupted. Progress saved per-ceiling file — rerun with --resume to continue.")
        return 1
    except ModelClientError:
        return 1

    summary_path = args.output_dir / "ceiling_comparison_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nSaved summary: {summary_path}")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())