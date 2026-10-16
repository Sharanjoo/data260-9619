"""HW6 Part 2: hold a 12-message conversation in ONE session through POST /api/chat,
then print GET /api/memory/{user_id} and GET /api/aggregate/{user_id}.

Needs the stack running (docker compose up -d) and Ollama running with qwen3:8b and
nomic-embed-text. Run from the repo root through the recorder so your name and timestamps
land in reports/hw06/RUN_LOG.txt:

    python scripts/recorded_run_hw06.py -- python scripts/demo_chat_hw06.py

The raw JSON of every turn plus the final memory/aggregate views is saved to
reports/hw06/raw/part2_*.json.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests

BASE = os.environ.get("HW6_BASE_URL", "http://localhost:8619").rstrip("/")
RAW = Path(__file__).resolve().parents[1] / "reports/hw06/raw"

CONVERSATION = [
    "Hi! I'm Jo. I live in San Jose and I shop at Safeway and Whole Foods.",
    "I have a severe peanut allergy, so allergen alerts matter most to me.",
    "What kinds of recall notices should I watch for?",
    "I buy a lot of frozen berries for smoothies. Any risk there?",
    "I also have a toddler who drinks oat milk every day.",
    "Explain the difference between a food-safety recall and a quality withdrawal.",
    "I prefer short answers and a weekly email digest.",
    "Which of my stores should I check first?",
    "What should I do if I already ate a recalled product?",
    "My partner is lactose intolerant, by the way.",
    "Remind me what allergy I have.",
    "Summarize everything you know about me and my family.",
]


def short(text: str, n: int = 150) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 1] + "…"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--user", default=f"jo-{int(time.time())}", help="user_id (default: a fresh one per run)")
    args = parser.parse_args()
    RAW.mkdir(parents=True, exist_ok=True)

    print(f"HW6 Part 2 chat demo against {BASE}  (user_id={args.user})\n")
    session_id = None
    turns = []
    for number, message in enumerate(CONVERSATION, start=1):
        body = {"user_id": args.user, "message": message}
        if session_id:
            body["session_id"] = session_id
        r = requests.post(f"{BASE}/api/chat", json=body, timeout=600)
        if r.status_code != 200:
            print(f"[{number}] HTTP {r.status_code}: {r.text[:300]}")
            return 1
        data = r.json()
        session_id = data["session_id"]
        turns.append(data)
        used, m, ev = data["memory_used"], data["metrics"], data["memory_events"]
        print(f"[{number:02d}] USER: {message}")
        print(f"     ASSISTANT: {short(data['reply'])}")
        facts = [f"{e['fact']} ({e['similarity']})" for e in used["episodic"]]
        print(f"     used: window={used['short_term']['count']}/{used['short_term']['limit']} "
              f"session_summary={'yes' if used['long_term']['session_summary'] else 'no'} "
              f"lifetime_summary={'yes' if used['long_term']['lifetime_summary'] else 'no'} "
              f"retrieved_facts={facts or 'none'}")
        print(f"     stored: {[e['fact'] for e in ev['episodes_stored']] or 'no new facts'}"
              f"{'  | session summary updated' if ev['session_summary_updated'] else ''}"
              f"{'  | lifetime summary updated' if ev['lifetime_summary_updated'] else ''}"
              f"{'  | WARNINGS ' + str(ev['warnings']) if ev['warnings'] else ''}")
        print(f"     tokens: prompt={m['prompt_tokens']} completion={m['completion_tokens']} "
              f"latency={m['latency_ms']:.0f} ms\n")

    memory = requests.get(f"{BASE}/api/memory/{args.user}", timeout=30).json()
    aggregate = requests.get(f"{BASE}/api/aggregate/{args.user}", timeout=30).json()
    (RAW / "part2_chat_turns.json").write_text(json.dumps(turns, indent=2, ensure_ascii=False), encoding="utf-8")
    (RAW / "part2_memory.json").write_text(json.dumps(memory, indent=2, ensure_ascii=False), encoding="utf-8")
    (RAW / "part2_aggregate.json").write_text(json.dumps(aggregate, indent=2, ensure_ascii=False), encoding="utf-8")

    print("=== GET /api/memory/" + args.user + " (condensed) ===")
    print(f"messages returned: {len(memory['messages'])}   episodes returned: {len(memory['episodes'])}")
    print("session summary:\n" + (memory["session_summary"]["text"] if memory["session_summary"] else "(none)"))
    print("lifetime summary:\n" + (memory["lifetime_summary"]["text"] if memory["lifetime_summary"] else "(none yet)"))
    print("episodes:")
    for e in memory["episodes"][:8]:
        print(f"  - {e['fact']}  [importance {e['importance']}]")
    print("\n=== GET /api/aggregate/" + args.user + " ===")
    print(json.dumps({k: v for k, v in aggregate.items() if k != "recent_summaries"}, indent=2))
    print(f"recent summaries: {len(aggregate['recent_summaries'])}")
    print(f"\nSaved raw JSON to {RAW}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except requests.ConnectionError:
        print(f"Cannot reach {BASE}. Is the API running? (docker compose up -d)")
        sys.exit(2)
