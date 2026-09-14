"""CLI entry point that runs the Part 3 stateful Planner/Reviewer/Supervisor graph."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.model_client import ModelClientError, OllamaModelClient
from code.agent_graph.state import initialize_state
from code.agent_graph.workflow import build_workflow


def load_input(path: Path) -> tuple[str, str, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    title = str(data.get("title", "")).strip()
    content = str(data.get("content", "")).strip()
    email = str(data.get("email", "")).strip()
    if not title or not content:
        raise ValueError("Input file must contain non-empty title and content strings")
    return title, content, email


def _safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _safe(v) for k, v in value.items() if k != "llm"}
    return value


class _CorruptFirstCallClient:
    """Test hook: wraps the real client and corrupts only its first .complete()
    response (truncates the Planner's tags to 2 items), so the graph hits a
    real Pydantic ValidationError and has to retry. Every call after the first
    behaves normally."""

    def __init__(self, real_client):
        self._real_client = real_client
        self._corrupted_once = False

    def complete(self, *args, **kwargs):
        response = self._real_client.complete(*args, **kwargs)

        if self._corrupted_once:
            return response

        self._corrupted_once = True
        try:
            payload = json.loads(response) if isinstance(response, str) else response
            if isinstance(payload, dict) and isinstance(payload.get("tags"), list):
                payload["tags"] = payload["tags"][:2]
                print("---TEST HOOK: corrupted first Planner response (tags truncated to 2)---")
                return json.dumps(payload) if isinstance(response, str) else payload
        except (json.JSONDecodeError, TypeError):
            pass
        return response

    def __getattr__(self, name):
        # Forward anything else (e.g. stats/attributes) to the real client.
        return getattr(self._real_client, name)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-file", type=Path)
    parser.add_argument("--title")
    parser.add_argument("--content")
    parser.add_argument("--email", default="")
    parser.add_argument("--model", default=os.getenv("OLLAMA_MODEL", "qwen3:8b"))
    parser.add_argument("--base-url", default=os.getenv("OLLAMA_URL", "http://localhost:11434"))
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--turn-ceiling", type=int, default=10)
    parser.add_argument(
        "--force-reviewer-issue",
        action="store_true",
        help="test hook: make the Reviewer always report an issue, to watch the correction loop",
    )
    parser.add_argument(
        "--force-planner-invalid-once",
        action="store_true",
        help="test hook: corrupt the first Planner response so it fails real schema validation, to prove the retry path works",
    )
    parser.add_argument("--output-json", type=Path)
    args = parser.parse_args()

    if args.input_file:
        title, content, email = load_input(args.input_file)
    elif args.title and args.content:
        title, content, email = args.title.strip(), args.content.strip(), args.email
    else:
        parser.error("provide --input-file or both --title and --content")

    client = OllamaModelClient(model=args.model, base_url=args.base_url)

    if args.force_planner_invalid_once:
        client = _CorruptFirstCallClient(client)

    reviewer_override = None
    if args.force_reviewer_issue:
        def _always_issue(state):
            print("---NODE: Reviewer (forced issue for loop test)---")
            return {
                "reviewer_feedback": {
                    "has_issues": True,
                    "explanation": "Forced issue for testing the correction loop.",
                }
            }
        reviewer_override = _always_issue

    workflow = build_workflow(reviewer_fn=reviewer_override)
    initial_state = initialize_state(
        title=title,
        content=content,
        email=email,
        llm=client,
        strict=args.strict,
        turn_ceiling=args.turn_ceiling,
    )

    final_state: Dict[str, Any] = dict(initial_state)
    try:
        for state_snapshot in workflow.stream(initial_state, stream_mode="values"):
            print("--- state snapshot ---")
            print(json.dumps(_safe(state_snapshot), indent=2, ensure_ascii=False, default=str))
            final_state = state_snapshot
    except ModelClientError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    result = {
        "input": {"title": title, "content": content, "email": email},
        "model": args.model,
        "turn_ceiling": args.turn_ceiling,
        "turn_count": final_state.get("turn_count"),
        "planner_proposal": final_state.get("planner_proposal"),
        "reviewer_feedback": final_state.get("reviewer_feedback"),
    }
    print("\n=== Final Result ===")
    print(json.dumps(result, indent=2, ensure_ascii=False))

    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"\nSaved machine-readable result: {args.output_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())