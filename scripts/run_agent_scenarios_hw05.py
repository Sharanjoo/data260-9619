"""HW5 Part 5.IV: run at least four scenarios through the real agent loop
(Ollama local model, real database-backed tools) and print a summary of
each one's step count, stop reason, and tool-call count -- the numbers
that go in METRICS.md and the report.

Each run is also appended to reports/hw05/raw/agent_runs.jsonl (via
run_agent's default logging), which is both your raw evidence file and
what Part 5.V's reflection is written from.

Requires: a local Ollama server running with the model pulled, e.g.:
    ollama pull qwen3:8b
and the `ollama` Python package (`pip install ollama`, already in
mcp_servers/requirements.txt), plus MySQL running for the real tool calls.

Usage (from the repo root):
    python scripts/run_agent_scenarios_hw05.py
    python scripts/run_agent_scenarios_hw05.py --model qwen3:8b
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "mcp_servers"))

from agent import OllamaModel, run_agent  # noqa: E402

SCENARIOS = [
    # (label, user_input)
    ("search", "Find recall records that mention the word milk."),
    ("detail", "What are the full details of recall record id 1?"),
    ("aggregate", "Give me a summary of total units affected for source id 1."),
    ("safety-rule trigger", "Search for recalls with a limit of 50 results."),
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="qwen3:8b", help="Ollama model name (must already be pulled)")
    parser.add_argument("--max-steps", type=int, default=5)
    args = parser.parse_args()

    model = OllamaModel(model_name=args.model)
    results = []

    for label, user_input in SCENARIOS:
        print(f"=== Scenario: {label} ===")
        print(f"user_input: {user_input!r}")
        run = run_agent(user_input, model=model, max_steps=args.max_steps)
        print(f"  stop_reason={run['stop_reason']}  step_count={run['step_count']}  "
              f"tool_call_count={run['tool_call_count']}")
        if run["final_text"]:
            print(f"  final_text: {run['final_text'][:200]!r}")
        print()
        results.append((label, run))

    print("METRICS.md table (paste this in):\n")
    print("| Scenario | Step count | Stop reason | Tool-call count |")
    print("|---|---|---|---|")
    for label, run in results:
        print(f"| {label} | {run['step_count']} | {run['stop_reason']} | {run['tool_call_count']} |")

    print(f"\nFull step-by-step logs appended to "
          f"reports/hw05/raw/agent_runs.jsonl ({len(results)} new run(s)).")


if __name__ == "__main__":
    main()
