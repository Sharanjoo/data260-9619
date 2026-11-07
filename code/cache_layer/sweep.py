"""HW9 Part 3.2-3.4: classify one case at one threshold, summarise a threshold, and price it.

Definitions (written down before any sweep was run):
  served       the nearest cached query has similarity >= threshold, so the cache answers
  correct hit  served, the case is labeled 'hit' and the nearest cached query is the one it should match
  false hit    served, but not a correct hit: any served 'miss' case (look-alike, unrelated) or a 'hit' case that
               landed on the wrong cached entry
  false miss   a 'hit' case that was not served (the agents ran although the cache could have answered)
  hit rate        served / all 40 cases
  false-hit rate  false hits / the 20 cases labeled 'miss'
  mean latency    mean over the 40 cases of: embed + search (+ the measured agent latency of that query when not served)
  total cost      (cases not served) x c_miss + (false hits) x c_false"""
from __future__ import annotations

from typing import Optional

from cache_layer.judge import answer_has_fact


def classify(case: dict, similarity: float, nearest: Optional[dict], base_queries: dict, threshold: float) -> dict:
    served = nearest is not None and similarity >= threshold
    want_hit = case["expected"] == "hit"
    right_entry = bool(served and want_hit and nearest["query"] == base_queries[case["expected_match"]])
    answer_ok = answer_has_fact(nearest["answer"], case.get("fact")) if served else None
    return {"served": served, "correct_hit": right_entry, "false_hit": bool(served and not right_entry),
            "false_miss": bool(want_hit and not served), "served_answer_has_right_fact": answer_ok}


def summarize(rows: list, c_miss: float, c_false: float) -> dict:
    n = len(rows)
    served = sum(r["served"] for r in rows)
    false_hits = sum(r["false_hit"] for r in rows)
    should_miss = sum(1 for r in rows if r["expected"] == "miss")
    not_served = n - served
    return {
        "cases": n, "served": served, "hit_rate": round(served / n, 4),
        "correct_hits": sum(r["correct_hit"] for r in rows), "false_hits": false_hits,
        "false_hit_rate": round(false_hits / should_miss, 4) if should_miss else None,
        "false_misses": sum(r["false_miss"] for r in rows),
        "wrong_answers_served": sum(1 for r in rows if r["served"] and r["served_answer_has_right_fact"] is False),
        "mean_latency_ms": round(sum(r["latency_ms"] for r in rows) / n, 1),
        "not_served": not_served,
        "total_cost": round(not_served * c_miss + false_hits * c_false, 4),
    }
