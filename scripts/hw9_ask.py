"""HW9: ask one question through the semantic cache (in front of the HW8 pipeline).

    python scripts/hw9_ask.py "How many units were affected by recall REC-015022 (Salad Kit (Lot 00016), ...)?"
    python scripts/hw9_ask.py "..." --threshold 0.90 --check-version
    python scripts/hw9_ask.py "..." --no-cache            (always runs the agents; nothing is read or stored)

The agents (Planner, Writer, Reviewer) must be running for a miss."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "code"))

import redis  # noqa: E402

from cache_layer.agent_client import AgentClient  # noqa: E402
from cache_layer.config import BANNER, DEFAULT_THRESHOLD, REDIS_HOST, REDIS_PORT  # noqa: E402
from cache_layer.embedder import Embedder  # noqa: E402
from cache_layer.facts import FactsStore  # noqa: E402
from cache_layer.ingress import SemanticIngress  # noqa: E402
from cache_layer.semantic_cache import SemanticCache  # noqa: E402


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("query")
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    parser.add_argument("--check-version", action="store_true", help="treat a hit whose record changed as stale")
    parser.add_argument("--no-cache", action="store_true")
    args = parser.parse_args()
    print(BANNER + " | hw9_ask", flush=True)

    cache = SemanticCache(redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True))
    cache.ensure_index()
    embedder = Embedder()
    embedder.encode("warm up")
    agent = AgentClient()
    await agent.start()
    try:
        ingress = SemanticIngress(cache, embedder, FactsStore(), agent, threshold=args.threshold)
        res = await ingress.answer(args.query, use_cache=not args.no_cache, check_version=args.check_version)
    finally:
        await agent.stop()
    keys = ("is_cached", "similarity", "threshold", "latency_ms", "timings", "status", "depends_on", "matched_query",
            "stale_entry_removed", "answer")
    print(json.dumps({k: res.get(k) for k in keys}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
