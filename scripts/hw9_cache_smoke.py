"""HW9 Part 2 smoke test of the Redis side: embedding model + vector index + KNN lookup (no Kafka, no agents).

    python scripts/hw9_cache_smoke.py

Needs docker compose up -d redis (redis-stack). Uses made-up sentences and removes only its own cache keys at the end."""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "code"))

import redis  # noqa: E402

from cache_layer.config import BANNER, CACHE_INDEX, REDIS_HOST, REDIS_PORT  # noqa: E402
from cache_layer.embedder import Embedder  # noqa: E402
from cache_layer.semantic_cache import SemanticCache  # noqa: E402


def main() -> int:
    print(BANNER + " | hw9_cache_smoke", flush=True)
    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    r.ping()
    modules = [m.get("name") for m in r.module_list()] if hasattr(r, "module_list") else []
    print(f"redis {REDIS_HOST}:{REDIS_PORT} modules: {modules}")
    cache = SemanticCache(r)
    print("index created now" if cache.ensure_index() else f"index {CACHE_INDEX} already exists")
    removed = cache.clear()
    print(f"removed {removed} old cache entries")

    t = time.perf_counter()
    emb = Embedder()
    emb.encode("warm up")
    print(f"embedding model {emb.model_name} loaded in {time.perf_counter() - t:.1f} s")

    stored = "How many units were affected by recall REC-900001 (Sample Soup, Test Brand)?"
    cache.store(stored, emb.encode_bytes(stored), "stored answer")
    probes = [
        ("identical", stored),
        ("reworded", "What is the number of units in the Test Brand Sample Soup recall REC-900001?"),
        ("same wording, other record", "How many units were affected by recall REC-900002 (Sample Stew, Other Brand)?"),
        ("different topic", "How do stores tell customers about a supply shortage?"),
    ]
    print(f"\nentries in cache: {cache.size()}   stored query: {stored!r}\n")
    sims = {}
    for label, text in probes:
        t = time.perf_counter()
        entry, sim = cache.lookup(emb.encode_bytes(text))
        ms = (time.perf_counter() - t) * 1000
        sims[label] = sim
        print(f"{label:<28} similarity={sim:.4f}  ({ms:.1f} ms incl. embedding)  nearest={entry['query'][:50]!r}")
    ok = sims["identical"] > 0.999 and sims["identical"] > sims["reworded"] > sims["different topic"]
    print("\nPASS: identical ~1.0 and ordering identical > reworded > different topic" if ok
          else "\nFAIL: unexpected similarity ordering")
    cache.clear()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
