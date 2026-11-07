"""HW9 Part 3.2: run the 40 labeled cases against the Redis cache at thresholds 0.75 .. 0.95.

    python scripts/recorded_run_hw09.py -- python scripts/hw9_part3_sweep.py

Needs reports/hw09/raw/part3_agent_pass.jsonl (hw9_part3_agent_pass.py). The 20 cached questions are loaded into Redis with
the answers the agents gave; then each case is embedded and searched in Redis (real, timed) at every threshold. When a case is
NOT served from the cache, the agents would have run, so its latency is the measured search time plus the agent latency that
the same question took in the agent pass (a replay: the agents are not run 200 times).

Writes raw/part3_similarities.csv (nearest cached query and similarity for every case), raw/part3_sweep_cases.csv and
raw/part3_sweep.json."""
from __future__ import annotations

import csv
import json
import sys
import time
from pathlib import Path

import redis
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "code"))

from cache_layer.config import BANNER, REDIS_HOST, REDIS_PORT  # noqa: E402
from cache_layer.embedder import Embedder  # noqa: E402
from cache_layer.semantic_cache import SemanticCache  # noqa: E402
from cache_layer.sweep import classify, summarize  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "reports" / "hw09" / "raw"
THRESHOLDS = [0.75, 0.80, 0.85, 0.90, 0.95]
C_MISS, C_FALSE = 0.01, 5.00  # placeholders for the table; the priced version is hw9_part3_cost.py (3.4)


def main() -> int:
    print(BANNER + " | hw9_part3_sweep", flush=True)
    doc = yaml.safe_load((ROOT / "data" / "hw09" / "cache_cases.yaml").read_text(encoding="utf-8"))
    passed = {}
    for line in (RAW / "part3_agent_pass.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            if row["status"] == "approved":
                passed[row["query"]] = row
    base_queries = {c["id"]: c["query"] for c in doc["cached_queries"]}
    missing = [q for q in [c["query"] for c in doc["cached_queries"]] + [c["query"] for c in doc["cases"]] if q not in passed]
    if missing:
        print(f"{len(set(missing))} question(s) have no approved agent answer yet - run hw9_part3_agent_pass.py first")
        return 1

    cache = SemanticCache(redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True))
    cache.ensure_index()
    print(f"cleared {cache.clear()} old cache entries")
    emb = Embedder()
    emb.encode("warm up")
    for c in doc["cached_queries"]:
        p = passed[c["query"]]
        cache.store(c["query"], emb.encode_bytes(c["query"]), p["answer"], data_version=p["data_version"],
                    depends_on=p["depends_on"])
    print(f"cache holds {cache.size()} entries (the 20 cached questions)\n", flush=True)

    sims, detail, summaries = [], [], {}
    for thr in THRESHOLDS:
        rows = []
        for case in doc["cases"]:
            t = time.perf_counter()
            vec = emb.encode_bytes(case["query"])
            t_embed = (time.perf_counter() - t) * 1000
            t = time.perf_counter()
            nearest, sim = cache.lookup(vec)
            t_search = (time.perf_counter() - t) * 1000
            res = classify(case, sim, nearest, base_queries, thr)
            latency = t_embed + t_search + (0.0 if res["served"] else float(passed[case["query"]]["agent_latency_ms"]))
            row = {"threshold": thr, "id": case["id"], "group": case["group"], "expected": case["expected"],
                   "similarity": sim, "nearest_query": nearest["query"] if nearest else None,
                   "embed_ms": round(t_embed, 2), "search_ms": round(t_search, 2), "latency_ms": round(latency, 2), **res}
            rows.append(row)
            detail.append(row)
            if thr == THRESHOLDS[0]:
                sims.append({"id": case["id"], "group": case["group"], "expected": case["expected"],
                             "similarity": sim, "query": case["query"], "nearest_query": row["nearest_query"]})
        summaries[str(thr)] = summarize(rows, C_MISS, C_FALSE)
    cache.clear()

    with (RAW / "part3_similarities.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(sims[0]))
        w.writeheader()
        w.writerows(sims)
    with (RAW / "part3_sweep_cases.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(detail[0]))
        w.writeheader()
        w.writerows(detail)
    (RAW / "part3_sweep.json").write_text(json.dumps({"thresholds": THRESHOLDS, "summaries": summaries}, indent=2),
                                          encoding="utf-8")

    print("similarity of the nearest cached question, by group (min / mean / max):")
    for g in ("exact_duplicate", "paraphrase", "lookalike", "unrelated"):
        xs = [s["similarity"] for s in sims if s["group"] == g]
        print(f"  {g:<16} {min(xs):.4f} / {sum(xs) / len(xs):.4f} / {max(xs):.4f}")
    print(f"\n{'threshold':>9} {'hit rate':>9} {'false-hit':>10} {'false hits':>10} {'false miss':>10} {'mean latency ms':>16}")
    for thr in THRESHOLDS:
        s = summaries[str(thr)]
        print(f"{thr:>9.2f} {s['hit_rate'] * 100:>8.1f}% {s['false_hit_rate'] * 100:>9.1f}% {s['false_hits']:>10} "
              f"{s['false_misses']:>10} {s['mean_latency_ms']:>16.1f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
