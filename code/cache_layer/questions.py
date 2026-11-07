"""HW9: the wording of the questions about one recall record. The cache cases (cache_cases.yaml), the Part 2 queries
and the stale-answer demo all draw from these, so a 'paraphrase' always means the same question asked another way."""
from __future__ import annotations

UNITS_BASE = "How many units were affected by recall {code} ({product}, {brand})?"
AGENCY_BASE = "Which agency reported recall {code} for {product} from {brand}?"

UNITS_PARAPHRASES = [
    "What is the total number of units covered by the {brand} {product} recall, record {code}?",
    "For recall {code} of {product} by {brand}, how many units were involved?",
    "Can you tell me the unit count for the {code} recall of {brand} {product}?",
    "How big was the {product} recall from {brand} ({code}) in units?",
    "{code}: how many units of {product} ({brand}) were recalled?",
]
AGENCY_PARAPHRASES = [
    "Who reported the {brand} {product} recall {code}?",
    "Which organisation filed recall {code} covering {product} from {brand}?",
    "Recall {code} for {brand} {product}: which agency was the source of the report?",
    "Which reporting agency is behind recall {code} ({product}, {brand})?",
    "Name the agency that reported the {code} recall of {product} by {brand}.",
]


def fill(template: str, rec: dict) -> str:
    return template.format(code=rec["record_code"], product=rec["product_name"], brand=rec["brand_name"])


def units_question(rec: dict) -> str:
    return fill(UNITS_BASE, rec)


def agency_question(rec: dict) -> str:
    return fill(AGENCY_BASE, rec)


def units_paraphrase(rec: dict, variant: int) -> str:
    return fill(UNITS_PARAPHRASES[variant % len(UNITS_PARAPHRASES)], rec)


def agency_paraphrase(rec: dict, variant: int) -> str:
    return fill(AGENCY_PARAPHRASES[variant % len(AGENCY_PARAPHRASES)], rec)


GENERAL_1 = "What should I do with a recalled product I already bought?"
GENERAL_1_PARAPHRASE = "I already bought a recalled item. What do I do with it?"
GENERAL_2 = "Where can I read the official recall notices?"


def part2_queries(p: list) -> list:
    """The 14 Part 2 demonstration queries (p = the six 'part2' records). 'expected' is what the query was MEANT to
    test; the run reports what actually happened."""
    def q(text: str, kind: str, expected: str, repeat_of: int | None = None) -> dict:
        return {"query": text, "kind": kind, "expected": expected, "repeat_of": repeat_of}

    return [
        q(units_question(p[0]), "new", "miss"),                                              # 1
        q(units_question(p[0]), "exact duplicate of 1", "hit", 1),                           # 2
        q(agency_question(p[1]), "new", "miss"),                                             # 3
        q(units_paraphrase(p[0], 0), "paraphrase of 1", "hit", 1),                           # 4
        q(GENERAL_1, "new", "miss"),                                                         # 5
        q(agency_question(p[1]), "exact duplicate of 3", "hit", 3),                          # 6
        q(units_question(p[2]), "new", "miss"),                                              # 7
        q(agency_paraphrase(p[1], 0), "paraphrase of 3", "hit", 3),                          # 8
        q(GENERAL_1_PARAPHRASE, "paraphrase of 5", "hit", 5),                                # 9
        q(GENERAL_2, "completely new", "miss"),                                              # 10
        q(units_question(p[3]), "new", "miss"),                                              # 11
        q(units_question(p[2]), "exact duplicate of 7", "hit", 7),                           # 12
        q(units_paraphrase(p[3], 1), "paraphrase of 11", "hit", 11),                         # 13
        q(agency_question(p[4]), "new", "miss"),                                             # 14
    ]
