"""HW9 Part 3 offline checks for the answer judge and the sweep definitions (python scripts/test_hw9_sweep.py)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "code"))

from cache_layer.judge import answer_has_fact  # noqa: E402
from cache_layer.sweep import classify, summarize  # noqa: E402

passed = failed = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global passed, failed
    passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))


U = {"aspect": "units", "record_code": "REC-1", "value": 31863}
A = {"aspect": "agency", "record_code": "REC-1", "value": "Regional Poison Control Center #162"}

# judge
check("units written without a comma", answer_has_fact("It affected 31863 units.", U) is True)
check("units written with a thousands comma", answer_has_fact("It affected 31,863 units.", U) is True)
check("a different number is wrong", answer_has_fact("It affected 43,025 units.", U) is False)
check("the number inside a longer number does not count", answer_has_fact("It affected 131863 units.", U) is False
      and answer_has_fact("It affected 31,8630 units.", U) is False)
check("units at the end of a sentence", answer_has_fact("Units affected: 31,863.", U) is True)
check("agency name, any case", answer_has_fact("reported by regional poison control center #162 (Midwest)", A) is True)
check("another agency number is wrong", answer_has_fact("reported by Regional Poison Control Center #166", A) is False)
check("no fact for an unrelated question", answer_has_fact("anything", None) is None)
check("an empty answer is wrong", answer_has_fact("", U) is False and answer_has_fact(None, U) is False)

# classify
base = {"B01": "q-base-1", "B02": "q-base-2"}
entry = {"query": "q-base-1", "answer": "31,863 units were affected."}
exact = {"expected": "hit", "expected_match": "B01", "fact": U}
look = {"expected": "miss", "fact": {"aspect": "units", "record_code": "REC-2", "value": 43025}}
unrel = {"expected": "miss"}
c = classify(exact, 1.0, entry, base, 0.85)
check("exact duplicate above threshold: correct hit", c["correct_hit"] and not c["false_hit"] and c["served_answer_has_right_fact"] is True)
c = classify(exact, 0.80, entry, base, 0.85)
check("a should-hit case below the threshold is a false miss", c["false_miss"] and not c["served"] and not c["false_hit"])
c = classify(look, 0.89, entry, base, 0.85)
check("a look-alike served from cache is a false hit with the wrong fact",
      c["false_hit"] and not c["correct_hit"] and c["served_answer_has_right_fact"] is False)
c = classify(look, 0.89, entry, base, 0.90)
check("the same look-alike below the threshold is a normal miss", not c["served"] and not c["false_hit"] and not c["false_miss"])
c = classify(unrel, 0.30, entry, base, 0.75)
check("an unrelated question below every threshold is a normal miss", not c["served"] and not c["false_hit"])
wrong_entry = {"query": "q-base-2", "answer": "x"}
c = classify(exact, 0.95, wrong_entry, base, 0.85)
check("a should-hit case served by the wrong cached entry is a false hit", c["false_hit"] and not c["correct_hit"])
c = classify(exact, 0.0, None, base, 0.85)
check("an empty cache serves nothing", not c["served"] and c["false_miss"])

# summarize
rows = []
for i in range(40):
    kind = "hit" if i < 20 else "miss"
    rows.append({"expected": kind, "served": False, "correct_hit": False, "false_hit": False, "false_miss": kind == "hit",
                 "served_answer_has_right_fact": None, "latency_ms": 1000.0})
for r in rows[:15]:
    r.update(served=True, correct_hit=True, false_miss=False, latency_ms=50.0, served_answer_has_right_fact=True)
for r in rows[20:24]:
    r.update(served=True, false_hit=True, latency_ms=50.0, served_answer_has_right_fact=False)
s = summarize(rows, c_miss=0.01, c_false=5.0)
check("hit rate = served / 40", s["served"] == 19 and s["hit_rate"] == 0.475)
check("false-hit rate = false hits / the 20 should-miss cases", s["false_hits"] == 4 and s["false_hit_rate"] == 0.2)
check("false misses are the should-hit cases not served", s["false_misses"] == 5 and s["correct_hits"] == 15)
check("wrong answers served counts served answers without the right fact", s["wrong_answers_served"] == 4)
check("mean latency", s["mean_latency_ms"] == round((19 * 50 + 21 * 1000) / 40, 1), str(s["mean_latency_ms"]))
check("total cost = misses x c_miss + false hits x c_false", s["not_served"] == 21 and abs(s["total_cost"] - (21 * 0.01 + 4 * 5.0)) < 1e-9,
      str(s["total_cost"]))
print(f"\n{passed} passed, {failed} failed")
sys.exit(0 if failed == 0 else 1)
