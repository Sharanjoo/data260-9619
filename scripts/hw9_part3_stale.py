"""HW9 Part 3.5: a stale cached answer, and the invalidation that fixes it.

    python scripts/recorded_run_hw09.py -- python scripts/hw9_part3_stale.py

Record: the 'stale' record picked by hw9_pick_records.py. Question: how many units were affected by that recall.
  1. empty the cache, ask (miss: the agents answer from the database value and the answer is cached with a data version)
  2. UPDATE recall_record.units_affected for that one record
  3. ask again WITHOUT the version check -> the cache returns the OLD number (stale hit)
  4. ask again WITH the version check -> the changed record is detected, the stale entry is deleted, the agents answer again
  5. ask again WITH the version check -> a normal hit with the new number
  6. time 10 hits with and without the version check (the price of the strategy)
  7. restore the original value
The Planner, Writer and Reviewer must be running (steps 1 and 4 each take about 2.5 minutes)."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

import redis
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "code"))

from cache_layer.agent_client import AgentClient  # noqa: E402
from cache_layer.config import BANNER, REDIS_HOST, REDIS_PORT  # noqa: E402
from cache_layer.embedder import Embedder  # noqa: E402
from cache_layer.facts import FactsStore  # noqa: E402
from cache_layer.ingress import SemanticIngress  # noqa: E402
from cache_layer.judge import answer_has_fact  # noqa: E402
from cache_layer.questions import units_question  # noqa: E402
from cache_layer.semantic_cache import SemanticCache  # noqa: E402

from db import SessionLocal  # noqa: E402

RAW = Path(__file__).resolve().parent.parent / "reports" / "hw09" / "raw"


def show(step: str, res: dict, old: int, new: int) -> dict:
    has_old = answer_has_fact(res["answer"], {"aspect": "units", "value": old})
    has_new = answer_has_fact(res["answer"], {"aspect": "units", "value": new})
    print(f"\n[{step}] is_cached={res['is_cached']} similarity={res['similarity']} latency={res['latency_ms']:.1f} ms "
          f"stale_entry_removed={res['stale_entry_removed']}")
    print(f"     answer: {res['answer']}")
    print(f"     answer states the OLD value ({old}): {has_old}   the NEW value ({new}): {has_new}", flush=True)
    return {"is_cached": res["is_cached"], "similarity": res["similarity"], "latency_ms": res["latency_ms"],
            "stale_entry_removed": res["stale_entry_removed"], "answer": res["answer"], "has_old_value": has_old,
            "has_new_value": has_new, "timings": res["timings"]}


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--increase", type=int, default=3000, help="how many units to add to the record")
    args = parser.parse_args()
    print(BANNER + " | hw9_part3_stale", flush=True)
    rec = json.loads((RAW / "records_picked.json").read_text(encoding="utf-8"))["groups"]["stale"][0]
    query = units_question(rec)
    old = rec["units_affected"]
    new = old + args.increase
    print(f"record {rec['record_code']}: {rec['product_name']} / {rec['brand_name']}\nquestion: {query}")

    def set_units(value: int) -> None:
        with SessionLocal() as s:
            s.execute(text("UPDATE recall_record SET units_affected = :u WHERE id = :i"), {"u": value, "i": rec["id"]})
            s.commit()

    with SessionLocal() as s:
        now = s.execute(text("SELECT units_affected FROM recall_record WHERE id = :i"), {"i": rec["id"]}).scalar()
    if now != old:
        print(f"database already holds {now}, not the seeded {old}; run hw9_seed_units.py or restore the value first")
        return 1

    cache = SemanticCache(redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True))
    cache.ensure_index()
    cache.clear()
    emb = Embedder()
    emb.encode("warm up")
    agent = AgentClient()
    await agent.start()
    ingress = SemanticIngress(cache, emb, FactsStore(), agent, threshold=0.85)
    out: dict = {"record": rec["record_code"], "query": query, "old_units": old, "new_units": new}
    try:
        out["1_first_ask"] = show(f"1 first ask - database holds {old}", await ingress.answer(query), old, new)
        set_units(new)
        print(f"\n>>> UPDATE recall_record SET units_affected = {new} WHERE record_code = '{rec['record_code']}'  (was {old})")
        out["3_stale_hit"] = show("3 same question, NO version check", await ingress.answer(query), old, new)
        out["4_with_check"] = show("4 same question, WITH version check", await ingress.answer(query, check_version=True), old, new)
        out["5_after_refresh"] = show("5 again, WITH version check", await ingress.answer(query, check_version=True), old, new)
        plain, checked = [], []
        for _ in range(10):
            t = time.perf_counter()
            await ingress.answer(query)
            plain.append((time.perf_counter() - t) * 1000)
            t = time.perf_counter()
            await ingress.answer(query, check_version=True)
            checked.append((time.perf_counter() - t) * 1000)
        out["6_cost_of_check"] = {"mean_ms_without_check": round(sum(plain) / 10, 2), "mean_ms_with_check": round(sum(checked) / 10, 2)}
        print(f"\n[6] 10 hits each: mean {out['6_cost_of_check']['mean_ms_without_check']} ms without the check, "
              f"{out['6_cost_of_check']['mean_ms_with_check']} ms with it")
    finally:
        set_units(old)
        print(f"\n>>> restored units_affected = {old}")
        cache.clear()
        await agent.stop()
    s3, s4, s5 = out["3_stale_hit"], out["4_with_check"], out["5_after_refresh"]
    out["checks"] = {
        "stale hit returned the old value": bool(s3["is_cached"] and s3["has_old_value"] and not s3["has_new_value"]),
        "version check removed the stale entry and re-ran the agents": bool(s4["stale_entry_removed"] and not s4["is_cached"]),
        "refreshed answer states the new value": bool(s4["has_new_value"] and not s4["has_old_value"]),
        "afterwards a normal hit with the new value": bool(s5["is_cached"] and s5["has_new_value"]),
    }
    (RAW / "part3_stale.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print("\n=== summary ===")
    for k, v in out["checks"].items():
        print(f"[{'PASS' if v else 'FAIL'}] {k}")
    return 0 if all(out["checks"].values()) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
