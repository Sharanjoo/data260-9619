"""HW9 Part 3.1: write data/hw09/cache_cases.yaml (40 labeled queries) from the picked records.

    python scripts/build_cache_cases_hw09.py

Deterministic: it only fills fixed question templates (code/cache_layer/questions.py) with the records chosen by
hw9_pick_records.py. The labels come from how each case is built, not from any similarity score:
  exact_duplicate (10)  the cached question, word for word                         -> hit
  paraphrase (10)       the same question about the same record, other wording     -> hit
  lookalike (10)        almost the same wording but a different correct answer     -> miss
                        (5: same question, a different lot of the same product; 5: same record, the other question)
  unrelated (10)        other grocery-recall questions that no cached question answers -> miss
The file is committed BEFORE any threshold sweep and never edited afterwards; a labeling mistake found later is
written to reports/hw09/LABEL_NOTES.md instead."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "code"))

from cache_layer.questions import (agency_paraphrase, agency_question, units_paraphrase,  # noqa: E402
                                   units_question)

PICKED = ROOT / "reports" / "hw09" / "raw" / "records_picked.json"
OUT = ROOT / "data" / "hw09" / "cache_cases.yaml"

UNRELATED = [
    "How do I find out whether my store sells a recalled product?",
    "What is the difference between a food safety recall and an allergen alert?",
    "How long does a grocery recall usually stay on the shelves?",
    "Can I get a refund for a recalled item without a receipt?",
    "What symptoms should I watch for after eating a recalled product?",
    "How should I store a recalled item until I return it?",
    "Who decides when a grocery product has to be recalled?",
    "What does a quality withdrawal mean for shoppers?",
    "How do stores tell customers about a supply shortage?",
    "Is it safe to donate recalled food to a food bank?",
]

HEADER = """# HW9 Part 3.1 - labeled test set for the semantic cache (40 queries).
# Written and committed BEFORE any threshold sweep. Labels are never changed afterwards; if a labeling mistake is
# found it is documented in reports/hw09/LABEL_NOTES.md instead of editing this file.
#
# cached_queries : the 20 questions whose answers are in the cache before the 40 cases run (B01..B20).
# cases          : group = exact_duplicate | paraphrase | lookalike | unrelated
#                  expected = hit (the cache should answer it) | miss (the agents must answer it)
#                  expected_match = the cached question a hit should return (hit cases only)
#                  fact = the database value that makes the answer correct (units_affected or the reporting agency)
# Fact values come from the MySQL rows chosen by scripts/hw9_pick_records.py (units_affected was 0 in every seeded row, so
# HW9 assigned fixed seeded values to those 32 records with scripts/hw9_seed_units.py).
"""


def fact_of(rec: dict, aspect: str) -> dict:
    if aspect == "units":
        return {"aspect": "units", "record_code": rec["record_code"], "value": rec["units_affected"]}
    return {"aspect": "agency", "record_code": rec["record_code"], "value": rec["source_name"]}


def ask(rec: dict, aspect: str) -> str:
    return units_question(rec) if aspect == "units" else agency_question(rec)


def paraphrase(rec: dict, aspect: str, variant: int) -> str:
    return units_paraphrase(rec, variant) if aspect == "units" else agency_paraphrase(rec, variant)


def build(groups: dict) -> dict:
    base, sibling = groups["base"], groups["sibling"]
    aspects = ["units" if i % 2 == 0 else "agency" for i in range(20)]
    cached = []
    for i, rec in enumerate(base):
        cached.append({"id": f"B{i + 1:02d}", "query": ask(rec, aspects[i]), "fact": fact_of(rec, aspects[i])})
    cases = []

    def add(group: str, expected: str, query: str, **extra) -> None:
        cases.append({"id": f"C{len(cases) + 1:02d}", "group": group, "expected": expected, "query": query, **extra})

    for i in range(10):
        add("exact_duplicate", "hit", cached[i]["query"], expected_match=cached[i]["id"], fact=dict(cached[i]["fact"]))
    for j in range(10):
        i = 10 + j
        add("paraphrase", "hit", paraphrase(base[i], aspects[i], j % 5), expected_match=cached[i]["id"],
            fact=dict(cached[i]["fact"]))
    for i in range(5):  # same question, a different lot of the same product
        add("lookalike", "miss", ask(sibling[i], aspects[i]), differs_from=cached[i]["id"],
            why="same question and product name, different lot, brand and agency", fact=fact_of(sibling[i], aspects[i]))
    for i in range(5, 10):  # same record, the other question
        other = "agency" if aspects[i] == "units" else "units"
        add("lookalike", "miss", ask(base[i], other), differs_from=cached[i]["id"],
            why=f"same record, asks for the {other} instead of the {aspects[i]}", fact=fact_of(base[i], other))
    for text in UNRELATED:
        add("unrelated", "miss", text)
    return {"meta": {"homework": 9, "sid4": "9619", "prefix": "s9619", "seed": 9619, "cases": len(cases),
                     "groups": {g: sum(1 for c in cases if c["group"] == g) for g in
                                ("exact_duplicate", "paraphrase", "lookalike", "unrelated")}},
            "cached_queries": cached, "cases": cases}


def check(doc: dict) -> None:
    cached = {c["id"]: c["query"] for c in doc["cached_queries"]}
    cases = doc["cases"]
    assert len(cached) == 20 and len(cases) == 40, (len(cached), len(cases))
    assert all(v == 10 for v in doc["meta"]["groups"].values()), doc["meta"]["groups"]
    for c in cases:
        if c["group"] == "exact_duplicate":
            assert c["query"] == cached[c["expected_match"]]
        if c["group"] == "paraphrase":
            assert c["query"] != cached[c["expected_match"]]
        if c["group"] in ("lookalike", "unrelated"):
            assert c["query"] not in cached.values(), c["id"]
        if c["group"] == "unrelated":
            assert "REC-" not in c["query"]
        assert (c["expected"] == "hit") == (c["group"] in ("exact_duplicate", "paraphrase"))
    assert len(set(cached.values())) == 20
    texts = [c["query"] for c in cases if c["group"] != "exact_duplicate"]
    assert len(set(texts)) == len(texts)


def main() -> int:
    groups = json.loads(PICKED.read_text(encoding="utf-8"))["groups"]
    doc = build(groups)
    check(doc)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    body = yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=120)
    OUT.write_text(HEADER + body, encoding="utf-8", newline="\n")
    print(f"written {OUT}: {doc['meta']['groups']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
