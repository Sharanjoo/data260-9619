"""Homework 2 Part 4: schema-validation classification experiment.

Runs the Part 3 stateful graph N times on a fixed input, classifying each
run by how many Planner attempts it took to produce a Reviewer-approved,
schema-valid proposal.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.model_client import ModelClientError, OllamaModelClient
from code.agent_graph.state import initialize_state
from code.agent_graph.workflow import build_workflow


def classify_run(planner_attempts: int, abandoned: bool) -> str:
    if abandoned:
        return "hit_turn_ceiling"
    if planner_attempts <= 1:
        return "valid_first_attempt"
    if planner_attempts == 2:
        return "valid_after_1_retry"
    return "valid_after_2plus_retries"


def run_once(title: str, content: str, email: str, model: str,
             base_url: str, turn_ceiling: int) -> Dict[str, Any]:
    from code.agent_graph.nodes import planner_node as real_planner_node

    client = OllamaModelClient(model=model, base_url=base_url)
    initial_state = initialize_state(
        title=title, content=content, email=email, llm=client, turn_ceiling=turn_ceiling,
    )

    attempt_counter = {"count": 0}

    def counting_planner(state):
        attempt_counter["count"] += 1
        return real_planner_node(state)

    workflow = build_workflow(planner_fn=counting_planner)

    start = time.perf_counter()
    final_state: Dict[str, Any] = dict(initial_state)
    for snapshot in workflow.stream(initial_state, stream_mode="values"):
        final_state = snapshot
    latency_ms = round((time.perf_counter() - start) * 1000, 3)

    planner_attempts = attempt_counter["count"]
    reviewer_feedback = final_state.get("reviewer_feedback")
    succeeded = (
        final_state.get("planner_proposal") is not None
        and reviewer_feedback is not None
        and not reviewer_feedback.get("has_issues")
    )
    abandoned = not succeeded

    return {
        "planner_attempts": planner_attempts,
        "turn_count": final_state.get("turn_count", 0),
        "abandoned": abandoned,
        "latency_ms": latency_ms,
        "final_planner_proposal": final_state.get("planner_proposal"),
        "final_reviewer_feedback": final_state.get("reviewer_feedback"),
        "classification": classify_run(planner_attempts, abandoned),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-file", type=Path, default=Path("reports/hw02/cases/schema_input.json"))
    parser.add_argument("--runs", type=int, default=30)
    parser.add_argument("--turn-ceiling", type=int, default=10)
    parser.add_argument("--model", default="qwen3:8b")
    parser.add_argument("--base-url", default="http://localhost:11434")
    parser.add_argument("--output-json", type=Path, default=Path("reports/hw02/raw/schema_classification_results.json"))
    parser.add_argument("--resume", action="store_true", help="skip runs already recorded in --output-json")
    args = parser.parse_args()

    data = json.loads(args.input_file.read_text(encoding="utf-8"))
    title, content, email = data["title"], data["content"], data.get("email", "")

    results: List[Dict[str, Any]] = []
    if args.resume and args.output_json.exists():
        existing = json.loads(args.output_json.read_text(encoding="utf-8"))
        results = existing.get("runs", [])
        print(f"Resuming: {len(results)} runs already recorded.")

    try:
        while len(results) < args.runs:
            run_index = len(results) + 1
            print(f"\n=== Run {run_index}/{args.runs} ===")
            try:
                result = run_once(title, content, email, args.model, args.base_url, args.turn_ceiling)
            except ModelClientError as exc:
                print(f"ERROR on run {run_index}: {exc}", file=sys.stderr)
                return 1
            print(json.dumps({k: v for k, v in result.items() if k not in ("final_planner_proposal", "final_reviewer_feedback")}, indent=2))
            results.append(result)

            args.output_json.parent.mkdir(parents=True, exist_ok=True)
            args.output_json.write_text(
                json.dumps({"turn_ceiling": args.turn_ceiling, "model": args.model, "runs": results}, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
    except KeyboardInterrupt:
        print("\nInterrupted. Progress saved — rerun with --resume to continue.")
        return 1

    # Summary
    from collections import Counter
    counts = Counter(r["classification"] for r in results)
    print("\n=== Summary over", len(results), "runs ===")
    for label in ("valid_first_attempt", "valid_after_1_retry", "valid_after_2plus_retries", "hit_turn_ceiling"):
        matching = [r["latency_ms"] for r in results if r["classification"] == label]
        mean_latency = round(sum(matching) / len(matching), 3) if matching else None
        print(f"{label}: count={counts.get(label, 0)}, mean_latency_ms={mean_latency}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())