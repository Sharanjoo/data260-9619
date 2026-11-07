"""HW9 Part 3.2 step 1: run every distinct question of cache_cases.yaml through the HW8 agent pipeline once, with the cache OFF.

    python scripts/recorded_run_hw09.py -- python scripts/hw9_part3_agent_pass.py

Why: the sweep needs (a) the final answer of each of the 20 cached questions to fill the cache, and (b) the real
agent latency of every query, so that a cache miss in the sweep can be priced with a measured number instead of a
guess. 50 distinct questions x about 2.5 minutes with qwen3:8b = about 2 hours. The Planner, Writer and Reviewer must be running.

Resumable: every finished question is appended to reports/hw09/raw/part3_agent_pass.jsonl; running the script again
skips the ones already approved. Nothing is read from or written to Redis."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "code"))

from cache_layer.agent_client import AgentClient  # noqa: E402
from cache_layer.config import BANNER  # noqa: E402
from cache_layer.facts import FactsStore  # noqa: E402
from cache_layer.ingress import SemanticIngress  # noqa: E402
from cache_layer.judge import answer_has_fact  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CASES = ROOT / "data" / "hw09" / "cache_cases.yaml"
OUT = ROOT / "reports" / "hw09" / "raw" / "part3_agent_pass.jsonl"


def distinct_questions(doc: dict) -> list:
    """(label, query, fact) for the 20 cached questions first, then every other distinct case query."""
    items, seen = [], set()
    for c in doc["cached_queries"]:
        items.append((c["id"], c["query"], c.get("fact")))
        seen.add(c["query"])
    for c in doc["cases"]:
        if c["query"] not in seen:
            items.append((c["id"], c["query"], c.get("fact")))
            seen.add(c["query"])
    return items


def load_done() -> dict:
    done = {}
    if OUT.exists():
        for line in OUT.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                if row.get("status") == "approved":
                    done[row["query"]] = row
    return done


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="stop after N new questions (0 = all)")
    args = parser.parse_args()
    print(BANNER + " | hw9_part3_agent_pass", flush=True)
    items = distinct_questions(yaml.safe_load(CASES.read_text(encoding="utf-8")))
    done = load_done()
    todo = [x for x in items if x[1] not in done]
    if args.limit:
        todo = todo[: args.limit]
    print(f"{len(items)} distinct questions, {len(done)} already approved, {len(todo)} to run", flush=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)

    agent = AgentClient()
    await agent.start()
    ingress = SemanticIngress(None, None, FactsStore(), agent)
    t0 = time.time()
    try:
        for n, (label, query, fact) in enumerate(todo, 1):
            print(f"\n--- {n}/{len(todo)} {label} ---\nQ: {query}", flush=True)
            res = await ingress.answer(query, use_cache=False, tag=label)
            row = {"label": label, "query": query, "answer": res["answer"], "status": res["status"],
                   "agent_latency_ms": res["timings"].get("agent_ms"), "correlation_id": res.get("correlation_id"),
                   "depends_on": res.get("depends_on"), "data_version": res.get("data_version"), "fact": fact,
                   "answer_has_fact": answer_has_fact(res["answer"], fact),
                   "started_at": res["started_at"], "finished_at": res["finished_at"]}
            with OUT.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            elapsed = time.time() - t0
            eta = elapsed / n * (len(todo) - n)
            print(f"status={row['status']}  agent {row['agent_latency_ms'] / 1000:.1f} s  answer_has_fact={row['answer_has_fact']}"
                  f"  (elapsed {elapsed / 60:.1f} min, about {eta / 60:.0f} min left)", flush=True)
            print(f"A: {row['answer']}", flush=True)
    finally:
        await agent.stop()
    now = load_done()
    left = [x for x in items if x[1] not in now]
    print(f"\napproved so far: {len(now)}/{len(items)}   not approved yet: {len(left)}")
    for label, query, _ in left:
        print(f"  not approved: {label} {query}")
    return 0 if not left else 2


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
