"""Interactive five-turn Ollama client with exact token accounting."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.model_client import ModelClientError, ModelResponse, OllamaModelClient


DEMO_PROMPTS = [
    "Review this Python function: def total(values): return sum(values)",
    "Review this JavaScript: const email = document.querySelector('#email').value;",
    "Review this Python: def first(items): return items[0]",
    "Review this JavaScript: localStorage.setItem('notice', JSON.stringify(data));",
    "Review this Python: data = json.loads(open('input.json').read())",
]


def is_bullet_only(text: str) -> bool:
    lines = [line for line in text.splitlines() if line.strip()]
    return bool(lines) and all(line.startswith("- ") for line in lines)


def serialized_history_length(history: list[dict[str, str]]) -> int:
    return len(json.dumps(history, ensure_ascii=False, separators=(",", ":")))


def print_turn(response: ModelResponse) -> None:
    print(response.content)
    print(
        "Turn tokens: "
        f"input={response.input_tokens}, output={response.output_tokens}, total={response.total_tokens}"
    )
    print(f"Bullet-only verification: {'PASS' if is_bullet_only(response.content) else 'FAIL'}")


def snapshot_stats(
    client: OllamaModelClient,
    history: list[dict[str, str]],
) -> dict[str, int]:
    stats: dict[str, Any] = client.stats()
    stats["serialized_history_length"] = serialized_history_length(history)
    return stats


def print_stats(client: OllamaModelClient, history: list[dict[str, str]]) -> dict[str, int]:
    stats = snapshot_stats(client, history)
    print("/stats")
    print(json.dumps(stats, indent=2))
    return stats


def send_turn(
    client: OllamaModelClient,
    history: list[dict[str, str]],
    prompt: str,
) -> dict[str, Any]:
    history.append({"role": "user", "content": prompt})
    response = client.complete(history)
    history.append({"role": "assistant", "content": response.content})
    print_turn(response)
    return {
        "prompt": prompt,
        "response": response.content,
        "input_tokens": response.input_tokens,
        "output_tokens": response.output_tokens,
        "total_tokens": response.total_tokens,
        "bullet_only": is_bullet_only(response.content),
        "serialized_history_length": serialized_history_length(history),
    }


def run_demo(client: OllamaModelClient, history: list[dict[str, str]]) -> dict[str, Any]:
    turns: list[dict[str, Any]] = []
    stats_snapshots: dict[str, dict[str, int]] = {}
    for turn_number, prompt in enumerate(DEMO_PROMPTS, start=1):
        print(f"\nUser turn {turn_number}: {prompt}")
        turn = send_turn(client, history, prompt)
        turn["turn"] = turn_number
        turns.append(turn)
        if turn_number in {3, 5}:
            stats_snapshots[str(turn_number)] = print_stats(client, history)
    return {"mode": "demo", "turns": turns, "stats_snapshots": stats_snapshots}


def run_interactive(client: OllamaModelClient, history: list[dict[str, str]]) -> dict[str, Any]:
    print("Enter code-review prompts. Commands: /stats, /quit")
    turns: list[dict[str, Any]] = []
    stats_snapshots: list[dict[str, int]] = []
    while True:
        try:
            prompt = input("you> ").strip()
        except EOFError:
            break
        if not prompt:
            continue
        if prompt == "/quit":
            break
        if prompt == "/stats":
            stats_snapshots.append(print_stats(client, history))
            continue
        turn = send_turn(client, history, prompt)
        turn["turn"] = len(turns) + 1
        turns.append(turn)
    return {"mode": "interactive", "turns": turns, "stats_snapshots": stats_snapshots}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", action="store_true", help="run the required five-turn conversation")
    parser.add_argument("--model", default=os.getenv("OLLAMA_MODEL", "qwen3:8b"))
    parser.add_argument("--base-url", default=os.getenv("OLLAMA_URL", "http://localhost:11434"))
    parser.add_argument("--agent-file", type=Path, default=Path("AGENT.md"))
    parser.add_argument("--output-json", type=Path, help="save per-turn usage and stats as JSON")
    args = parser.parse_args()

    system_prompt = args.agent_file.read_text(encoding="utf-8").strip()
    history = [{"role": "system", "content": system_prompt}]
    client = OllamaModelClient(model=args.model, base_url=args.base_url)
    run_data: dict[str, Any] = {"mode": "demo" if args.demo else "interactive", "turns": []}
    exit_code = 0

    try:
        if args.demo:
            run_data = run_demo(client, history)
        else:
            run_data = run_interactive(client, history)
    except ModelClientError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        run_data["error"] = str(exc)
        exit_code = 1
    finally:
        stats = client.stats()
        run_data.update(
            {
                "model": args.model,
                "agent_file": str(args.agent_file),
                "cumulative": stats,
            }
        )
        if args.output_json:
            args.output_json.parent.mkdir(parents=True, exist_ok=True)
            args.output_json.write_text(
                json.dumps(run_data, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            print(f"Saved per-turn token data: {args.output_json}")
        print(
            "Cumulative tokens on exit: "
            f"input={stats['input_tokens']}, output={stats['output_tokens']}, "
            f"turns={stats['turn_count']}"
        )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
