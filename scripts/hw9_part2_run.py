"""HW9 Part 2: 14 queries (new, exact duplicates, paraphrases) through the semantic cache in front of the HW8 pipeline.

Start first (as in HW8): docker compose up -d, then Planner, Writer and Reviewer in three terminals, and make sure
scripts/hw9_pick_records.py has written reports/hw09/raw/records_picked.json.

    python scripts/hw9_part2_run.py                 (threshold 0.85, as the assignment starts)
    python scripts/hw9_part2_run.py --threshold 0.85 --limit 4

Writes reports/hw09/raw/part2_queries.jsonl (one line per query: is_cached, similarity, latency, stage timings,
timestamps) and part2_summary.json (hit rate, mean latency of cached and of non-cached queries)."""
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
from cache_layer.questions import part2_queries  # noqa: E402
from cache_layer.semantic_cache import SemanticCache  # noqa: E402

RAW = Path(__file__).resolve().parent.parent / "reports" / "hw09" / "raw"


def mean(xs: list) -> float | None:
    return round(sum(xs) / len(xs), 2) if xs else None


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    parser.add_argument("--limit", type=int, default=0, help="run only the first N queries (0 = all 14)")
    args = parser.parse_args()
    print(BANNER + f" | hw9_part2_run threshold={args.threshold}", flush=True)

    picked = json.loads((RAW / "records_picked.json").read_text(encoding="utf-8"))["groups"]["part2"]
    queries = part2_queries(picked)[: args.limit or None]

    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    cache = SemanticCache(r)
    cache.ensure_index()
    print(f"cleared {cache.clear()} old cache entries (only keys under s9619:cache:)")
    metrics = RAW / "part2_queries.jsonl"
    metrics.parent.mkdir(parents=True, exist_ok=True)
    metrics.write_text("", encoding="utf-8")

    embedder = Embedder()
    embedder.encode("warm up")  # the model load must not count as the first query's latency
    agent = AgentClient()
    await agent.start()
    ingress = SemanticIngress(cache, embedder, FactsStore(), agent, threshold=args.threshold, metrics_path=metrics)
    results = []
    try:
        for n, item in enumerate(queries, 1):
            print(f"\n--- query {n}/{len(queries)} ({item['kind']}; meant to {item['expected']}) ---", flush=True)
            print(f"Q: {item['query']}", flush=True)
            res = await ingress.answer(item["query"], tag=f"q{n}")
            res.update(n=n, kind=item["kind"], expected=item["expected"])
            results.append(res)
            sim = "-" if res["similarity"] is None else f"{res['similarity']:.4f}"
            print(f"is_cached={res['is_cached']}  similarity={sim}  latency={res['latency_ms']:.1f} ms  "
                  f"status={res['status']}", flush=True)
            print(f"A: {res['answer']}", flush=True)
    finally:
        await agent.stop()

    cached = [x for x in results if x["is_cached"]]
    live = [x for x in results if not x["is_cached"]]
    summary = {
        "threshold": args.threshold, "queries": len(results), "cache_hits": len(cached),
        "hit_rate_percent": round(100 * len(cached) / len(results), 1) if results else None,
        "mean_latency_ms_cached": mean([x["latency_ms"] for x in cached]),
        "mean_latency_ms_not_cached": mean([x["latency_ms"] for x in live]),
        "met_expectation": sum(1 for x in results if x["is_cached"] == (x["expected"] == "hit")),
        "per_query": [{"n": x["n"], "kind": x["kind"], "expected": x["expected"], "is_cached": x["is_cached"],
                       "similarity": x["similarity"], "latency_ms": x["latency_ms"], "status": x["status"]}
                      for x in results],
    }
    (RAW / "part2_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print("\n=== Part 2 summary ===")
    print(f"queries: {summary['queries']}   served from cache: {summary['cache_hits']}   "
          f"hit rate: {summary['hit_rate_percent']}%")
    print(f"mean latency, cached: {summary['mean_latency_ms_cached']} ms   "
          f"not cached: {summary['mean_latency_ms_not_cached']} ms")
    print(f"queries that behaved as intended: {summary['met_expectation']}/{summary['queries']}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
