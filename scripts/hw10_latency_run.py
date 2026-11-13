"""HW10 Part 4.3: the stage-latency experiment. Sends fresh questions through the semantic cache (threshold 0.95, as shipped
in HW9) in front of the HW8 pipeline, one at a time, until 50 CONFIRMED cache misses have completed the agent path.

    python scripts/hw10_latency_run.py                  (miss phase, then 10 exact repeats as cache hits)
    python scripts/hw10_latency_run.py --target 50 --hits 10
    python scripts/hw10_latency_run.py --dry-run         (print the question pool only; no services)

Needs: docker compose up -d (Redis, Kafka, MySQL), Ollama, and the Planner, Writer and Reviewer running. Nothing else may use
Ollama while this runs (the latency numbers would include waiting for it). A request counts as a CONFIRMED MISS only if the cache
lookup said is_cached=false AND the agents ran AND the final status is approved; a question the cache answered anyway
(similarity >= threshold) is logged as 'hit_excluded' and the next question from the pool is used instead. The pool order is fixed
(seed 9619), results go to data/hw10/latency_runs.jsonl (one line per request) and the run can be resumed after a stop."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "code"))

from cache_layer.config import SEED  # noqa: E402

DATA = REPO / "data" / "hw10"
RUNS = DATA / "latency_runs.jsonl"
PICKED = REPO / "reports" / "hw09" / "raw" / "records_picked.json"
METRICS = REPO / "reports" / "hw10" / "raw" / "ingress_metrics.jsonl"
THRESHOLD = 0.95
BANNER = "Sharan Lourduraj | SID4 9619 | DATA 260 HW10 Part 4.3 (latency run)"

RECORD_TEMPLATES = [
    "What is the name of the brand behind recall {code} for {product}?",
    "In which region was recall {code} ({product}) reported?",
    "Give me a quick summary of recall {code}: {product} by {brand}.",
    "Which product does recall {code} cover, and what should shoppers do about it?",
]
GENERAL = [
    "My child ate a little of a recalled cereal. What symptoms should I watch for?",
    "How long should I keep a recalled item before throwing it away?",
    "Can I donate recalled canned goods to a food bank?",
    "Do recalled items sold at a farmers market follow the same rules as supermarket items?",
    "What does it mean when a recall is labelled Class I?",
    "Should I clean my refrigerator after storing a recalled product in it?",
    "Is a recalled product still dangerous after it has been frozen?",
    "How do I tell whether my store has removed a recalled product from the shelves?",
    "Who decides that a grocery product has to be recalled?",
    "Can a recalled product be fixed and sold again?",
    "I bought a recalled item as a gift. What should I tell the person I gave it to?",
    "Are recalled products safe to feed to backyard chickens?",
    "How can an elderly relative who does not use the internet find out about a recall?",
    "What should a restaurant do if it served a recalled ingredient by mistake?",
    "Will I get my money back if I throw a recalled product away without returning it?",
]


def build_pool() -> list:
    groups = json.loads(PICKED.read_text(encoding="utf-8"))["groups"]
    recs = [r for g in ("base", "sibling", "part2") for r in groups[g]]  # the 'stale' record is left alone
    rng = random.Random(SEED + 10)
    pairs = [(r, t) for r in recs for t in range(len(RECORD_TEMPLATES))]
    rng.shuffle(pairs)
    chosen = pairs[:62]
    items = [{"kind": "record", "text": RECORD_TEMPLATES[t].format(code=r["record_code"], product=r["product_name"],
                                                                    brand=r["brand_name"])} for r, t in chosen]
    items += [{"kind": "general", "text": q} for q in GENERAL]
    rng.shuffle(items)
    for i, it in enumerate(items, 1):
        it["n"] = i
    return items


def read_runs() -> list:
    if not RUNS.exists():
        return []
    return [json.loads(line) for line in RUNS.read_text(encoding="utf-8").splitlines() if line.strip()]


def append_run(rec: dict) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    with RUNS.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def warm_up_model() -> None:
    """Load qwen3:8b into memory so the first measured request does not pay the model load (not counted anywhere)."""
    t = time.perf_counter()
    model = os.environ.get("OLLAMA_MODEL", "qwen3:8b")
    body = json.dumps({"model": model, "prompt": "hi", "stream": False, "think": False, "keep_alive": "30m",
                       "options": {"num_predict": 1}}).encode()
    try:
        req = urllib.request.Request("http://localhost:11434/api/generate", data=body, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=300).read()
        print(f"warm-up: {model} loaded in {time.perf_counter() - t:.1f}s (not measured)", flush=True)
    except Exception as exc:  # noqa: BLE001
        print(f"warm-up skipped: {exc}", flush=True)


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=int, default=50, help="confirmed cache misses wanted")
    ap.add_argument("--hits", type=int, default=10, help="exact repeats to measure as cache hits afterwards")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    print(BANNER, flush=True)
    pool = build_pool()
    if args.dry_run:
        for it in pool:
            print(f"{it['n']:02d} [{it['kind']:7s}] {it['text']}")
        print(f"pool of {len(pool)} questions (the run stops at {args.target} confirmed misses)")
        return 0

    import redis
    from cache_layer.agent_client import AgentClient
    from cache_layer.config import REDIS_HOST, REDIS_PORT
    from cache_layer.embedder import Embedder
    from cache_layer.facts import FactsStore
    from cache_layer.ingress import SemanticIngress
    from cache_layer.semantic_cache import SemanticCache

    cache = SemanticCache(redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True))
    cache.ensure_index()
    embedder = Embedder()
    embedder.encode("warm up")
    warm_up_model()
    agent = AgentClient()
    await agent.start()
    runs = read_runs()
    asked = {r["text"] for r in runs if r["phase"] == "miss"}
    confirmed = [r for r in runs if r["phase"] == "miss" and r["kind_result"] == "confirmed_miss"]
    try:
        ingress = SemanticIngress(cache, embedder, FactsStore(), agent, threshold=THRESHOLD, metrics_path=METRICS)
        for it in pool:
            if len(confirmed) >= args.target:
                break
            if it["text"] in asked:
                continue
            res = await ingress.answer(it["text"], tag=f"lat-{it['n']}")
            ok_miss = (not res["is_cached"]) and res["status"] == "approved"
            kind = "hit_excluded" if res["is_cached"] else ("confirmed_miss" if ok_miss else "failed")
            rec = {"phase": "miss", "n": it["n"], "category": it["kind"], "text": it["text"], "trace_id": res["trace_id"],
                   "is_cached": res["is_cached"], "similarity": res["similarity"], "status": res["status"],
                   "latency_ms": res["latency_ms"], "kind_result": kind, "finished_at": res["finished_at"]}
            append_run(rec)
            asked.add(it["text"])
            if kind == "confirmed_miss":
                confirmed.append(rec)
            print(f"[{len(confirmed):02d}/{args.target}] #{it['n']:02d} {kind:14s} sim={res['similarity']:.3f} "
                  f"latency={res['latency_ms'] / 1000:.0f}s trace_id={res['trace_id']}", flush=True)
        print(f"confirmed cache misses: {len(confirmed)}/{args.target}")
        done_hits = [r for r in runs if r["phase"] == "hit"]
        todo = [r for r in confirmed[:args.hits] if r["text"] not in {h["text"] for h in done_hits}]
        for src in todo:
            res = await ingress.answer(src["text"], tag=f"hit-{src['n']}")
            append_run({"phase": "hit", "n": src["n"], "category": src["category"], "text": src["text"],
                        "trace_id": res["trace_id"], "is_cached": res["is_cached"], "similarity": res["similarity"],
                        "status": res["status"], "latency_ms": res["latency_ms"],
                        "kind_result": "hit" if res["is_cached"] else "repeat_not_hit", "finished_at": res["finished_at"]})
            print(f"hit repeat #{src['n']:02d} is_cached={res['is_cached']} sim={res['similarity']:.3f} "
                  f"latency={res['latency_ms']:.0f}ms trace_id={res['trace_id']}", flush=True)
    finally:
        await agent.stop()
    allr = read_runs()
    print("summary:", {k: sum(1 for r in allr if r["kind_result"] == k)
                       for k in ("confirmed_miss", "hit_excluded", "failed", "hit", "repeat_not_hit")})
    return 0 if len(confirmed) >= args.target else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
