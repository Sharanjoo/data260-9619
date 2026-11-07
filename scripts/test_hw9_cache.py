"""HW9 Parts 2-3 offline checks for the ingress logic (python scripts/test_hw9_cache.py).

The Redis vector search, the real embedding model and the Kafka agents are replaced by small stand-ins, so this proves
the decision logic only (hit / miss / threshold / what gets stored / stale handling / metrics). The real behaviour is
shown by scripts/hw9_cache_smoke.py (Redis index + embeddings) and by the recorded Part 2 and Part 3 runs."""
from __future__ import annotations

import asyncio
import json
import re
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "code"))

from cache_layer.facts import fingerprint, find_record_code  # noqa: E402
from cache_layer.ingress import SemanticIngress  # noqa: E402
from cache_layer.questions import (agency_paraphrase, agency_question, part2_queries, units_paraphrase,  # noqa: E402
                                   units_question)

passed = failed = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global passed, failed
    passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))


def unit(*xs: float) -> np.ndarray:
    v = np.zeros(384, dtype=np.float32)
    v[:len(xs)] = xs
    return v / np.linalg.norm(v)


class FakeEmbedder:
    def __init__(self, table: dict) -> None:
        self.table = table

    def encode_bytes(self, text: str) -> bytes:
        return self.table[text].tobytes()


class FakeCache:
    def __init__(self) -> None:
        self.rows: dict = {}

    def lookup(self, emb: bytes):
        v = np.frombuffer(emb, dtype=np.float32)
        best, best_sim = None, 0.0
        for key, row in self.rows.items():
            sim = float(np.dot(v, np.frombuffer(row["embedding"], dtype=np.float32)))
            if best is None or sim > best_sim:
                best, best_sim = dict(row, key=key), sim
        return best, round(best_sim, 6)

    def store(self, query, embedding, answer, data_version="none", depends_on="none"):
        key = "k:" + query
        self.rows[key] = {"query": query, "embedding": embedding, "answer": answer, "data_version": data_version,
                          "depends_on": depends_on, "created_at": "now"}
        return key

    def delete(self, key):
        return 1 if self.rows.pop(key, None) is not None else 0


class FakeFacts:
    def __init__(self, records: dict) -> None:
        self.records = records

    def load(self, code):
        return dict(self.records[code]) if code in self.records else None

    def version(self, code):
        f = self.load(code)
        return fingerprint(f) if f else None


class FakeAgent:
    def __init__(self, delay: float = 0.05) -> None:
        self.calls = 0
        self.status = "approved"
        self.timeout = False
        self.delay = delay
        self.questions: list = []

    async def run(self, question, correlation_id, entity_key=None):
        self.calls += 1
        self.questions.append((question, correlation_id, entity_key))
        await asyncio.sleep(self.delay)
        if self.timeout:
            return None
        m = re.search(r"units affected (\d+)", question)
        return {"correlation_id": correlation_id, "status": self.status,
                "answer": f"{m.group(1)} units were affected." if m else "Do not eat the recalled product."}


REC = {"record_code": "REC-015588", "product_name": "Cantaloupe (Lot 00582)", "brand_name": "Farmer's Market",
       "units_affected": 734, "source_name": "Agency 18", "source_region": "Midwest"}


async def main() -> int:
    q1 = units_question(REC)
    q1_para = units_paraphrase(REC, 0)
    q_other = "How do I find out whether my store sells a recalled product?"
    table = {q1: unit(1, 0, 0), q1_para: unit(0.95, 0.312249, 0), q_other: unit(0, 1, 0)}
    cos = float(np.dot(table[q1], table[q1_para]))
    facts = FakeFacts({REC["record_code"]: dict(REC)})
    cache, agent = FakeCache(), FakeAgent()
    tmp = Path(tempfile.mkdtemp(prefix="hw9_cache_")) / "m.jsonl"
    ing = SemanticIngress(cache, FakeEmbedder(table), facts, agent, threshold=0.85, metrics_path=tmp)

    r1 = await ing.answer(q1, tag="t1")
    check("first query is a miss: is_cached false, agent ran once", r1["is_cached"] is False and agent.calls == 1)
    check("the miss answer comes back and is stored with its dependency and version",
          r1["answer"] == "734 units were affected." and len(cache.rows) == 1
          and cache.rows["k:" + q1]["depends_on"] == "REC-015588"
          and cache.rows["k:" + q1]["data_version"] == fingerprint(REC))
    check("the agent got the question plus the database facts and the record code as entity key",
          "units affected 734" in agent.questions[0][0] and agent.questions[0][2] == "REC-015588")

    r2 = await ing.answer(q1)
    check("exact repeat is a hit with similarity ~1 and the agent is not run again",
          r2["is_cached"] is True and r2["similarity"] > 0.999 and agent.calls == 1)
    check("the hit returns the stored answer", r2["answer"] == r1["answer"])
    check("hit is much faster than the miss", r2["latency_ms"] < r1["latency_ms"] / 5,
          f"hit {r2['latency_ms']} ms, miss {r1['latency_ms']} ms")

    r3 = await ing.answer(q1_para)
    check("paraphrase above the threshold hits", r3["is_cached"] is True and abs(r3["similarity"] - cos) < 1e-4,
          f"similarity {r3['similarity']}")
    r3b = await ing.answer(q1_para, threshold=0.99)
    check("the same paraphrase misses when the threshold is raised above its similarity",
          r3b["is_cached"] is False and r3b["threshold"] == 0.99 and agent.calls == 2)

    n = agent.calls
    r4 = await ing.answer(q_other)
    check("an unrelated question misses and runs the agent", r4["is_cached"] is False and agent.calls == n + 1)
    check("a general question depends on no record", cache.rows["k:" + q_other]["depends_on"] == "none"
          and cache.rows["k:" + q_other]["data_version"] == "none")

    agent.status = "rejected"
    table["a new question"] = unit(0, 0, 1)
    r5 = await ing.answer("a new question")
    check("a rejected answer is returned but not stored", r5["status"] == "rejected" and "k:a new question" not in cache.rows)
    agent.status, agent.timeout = "approved", True
    table["another new question"] = unit(0, 0, 0, 1)
    r6 = await ing.answer("another new question")
    check("a pipeline timeout is reported and nothing is stored",
          r6["status"] == "timeout" and r6["answer"] is None and "k:another new question" not in cache.rows)
    agent.timeout = False

    # stale answer: the record changes after the answer was cached
    facts.records["REC-015588"]["units_affected"] = 9999
    calls = agent.calls
    r7 = await ing.answer(q1)
    check("without a version check the cache returns the OLD answer (stale hit)",
          r7["is_cached"] is True and r7["answer"] == "734 units were affected." and agent.calls == calls)
    r8 = await ing.answer(q1, check_version=True)
    check("with the version check the stale entry is removed and the agent runs again",
          r8["is_cached"] is False and r8["stale_entry_removed"] is True and agent.calls == calls + 1)
    check("the refreshed answer shows the new value", r8["answer"] == "9999 units were affected.")
    check("the entry now carries the new data version", cache.rows["k:" + q1]["data_version"] == fingerprint(facts.records["REC-015588"]))
    r9 = await ing.answer(q1, check_version=True)
    check("afterwards the same question is a normal hit with the new answer",
          r9["is_cached"] is True and r9["answer"] == "9999 units were affected." and agent.calls == calls + 1)
    check("the version check cost is recorded on a hit", "version_check_ms" in r9["timings"])

    lines = [json.loads(x) for x in tmp.read_text(encoding="utf-8").splitlines()]
    needed = {"query", "is_cached", "similarity", "latency_ms", "timings", "started_at", "finished_at", "threshold"}
    check("every call wrote one metrics line with flag, similarity, latency and timestamps",
          len(lines) == 10 and all(needed <= set(x) for x in lines), f"{len(lines)} lines")

    bumped = dict(REC, units_affected=735)
    check("the data version changes when the units change and not otherwise",
          fingerprint(REC) != fingerprint(bumped) and fingerprint(REC) == fingerprint(dict(REC, view_count=500)))
    check("record codes are found in any case", find_record_code("see rec-015588 please") == "REC-015588"
          and find_record_code("no code here") is None)
    check("a paraphrase of a question still names the record",
          REC["record_code"] in units_paraphrase(REC, 3) and REC["record_code"] in agency_paraphrase(REC, 4)
          and REC["record_code"] in agency_question(REC))
    recs = [dict(REC, record_code=f"REC-0155{i:02d}", product_name=f"Product {i} (Lot {i:05d})") for i in range(6)]
    qs = part2_queries(recs)
    texts = [x["query"] for x in qs]
    check("Part 2 has 14 queries covering new, exact duplicate and paraphrase cases",
          len(qs) == 14 and any("exact duplicate" in x["kind"] for x in qs)
          and any("paraphrase" in x["kind"] for x in qs) and sum(x["expected"] == "miss" for x in qs) == 7)
    check("every exact duplicate really is the same text as the query it repeats",
          all(texts[x["repeat_of"] - 1] == x["query"] for x in qs if x["kind"].startswith("exact duplicate")))
    check("every paraphrase differs in wording from the query it rephrases",
          all(texts[x["repeat_of"] - 1] != x["query"] for x in qs if x["kind"].startswith("paraphrase")))
    start = time.perf_counter()
    check("test run is quick", time.perf_counter() - start < 5)
    print(f"\n{passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
