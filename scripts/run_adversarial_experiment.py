"""Homework 2 Part 4 #5: adversarial input, 5 runs."""
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-file", type=Path, default=Path("reports/hw02/cases/adversarial_input.json"))
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--turn-ceiling", type=int, default=2)
    parser.add_argument("--model", default="qwen3:8b")
    parser.add_argument("--base-url", default="http://localhost:11434")
    parser.add_argument("--output-json", type=Path, default=Path("reports/hw02/raw/adversarial_results.json"))
    args = parser.parse_args()

    data = json.loads(args.input_file.read_text(encoding="utf-8"))
    title, content, email = data["title"], data["content"], data.get("email", "")

    results: List[Dict[str, Any]] = []
    try:
        for i in range(args.runs):
            print(f"\n=== adversarial run {i + 1}/{args.runs} ===")
            result = run_once(title, content, email, args.model, args.base_url, args.turn_ceiling)
            print(json.dumps(
                {k: v for k, v in result.items() if k not in ("final_planner_proposal", "final_reviewer_feedback")},
                indent=2,
            ))
            results.append(result)
    except ModelClientError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps({"turn_ceiling": args.turn_ceiling, "model": args.model, "runs": results}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    hit_ceiling = sum(1 for r in results if r["abandoned"])
    print(f"\n=== Summary: {hit_ceiling}/{len(results)} runs hit the turn ceiling ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())