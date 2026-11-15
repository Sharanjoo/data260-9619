"""HW10 Part 2 offline checks (python scripts/test_hw10_evaluator.py): the collector joins plan, draft and final by
correlation_id and survives bad messages; the evaluator scores, computes the final-vs-draft difference and never hangs on a
judge failure. In-memory Kafka and a scripted judge client stand in for Kafka and Ollama."""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import time
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "code"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

TMP = Path(tempfile.mkdtemp(prefix="hw10_eval_"))
os.environ["HW10_SPANS_PATH"] = str(TMP / "spans.jsonl")

from evaluation.collector import collect_many, load_bundles, make_bundle, save_bundles  # noqa: E402
from evaluation.evaluator import append_results, evaluate_bundle, interpret, load_results  # noqa: E402
from evaluation.judge import OllamaJudge  # noqa: E402
from evaluation.rubrics import build_metrics  # noqa: E402
from fake_kafka_hw08 import FakeBroker, FakeConsumer, FakeProducer  # noqa: E402
from kafka_agents.send_question import ask  # noqa: E402
from kafka_agents.settings import (DEAD_LETTER_TOPIC, DRAFTS_TOPIC, FINAL_TOPIC, INBOX_TOPIC, TASKS_PARTITIONS,  # noqa: E402
                                   TASKS_TOPIC, Flags)
from kafka_agents.runtime import run_stage  # noqa: E402
from kafka_agents.stages import make_planner, make_reviewer, make_writer  # noqa: E402
from tracing.spans import read_spans  # noqa: E402

passed = failed = 0
FAST = Flags(mode="fast", retry_backoff_s=0.01)
QUIET = lambda c, t: None  # noqa: E731


def check(name: str, ok: bool, detail: str = "") -> None:
    global passed, failed
    passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))


class Reply:
    def __init__(self, c): self.content = c  # noqa: E704


class ScriptedClient:
    """Answers every judge call with the next scripted reply (a JSON text or an Exception)."""

    def __init__(self, replies, default='{"score": 4, "reason": "ok"}'):
        self.replies, self.default, self.calls = list(replies), default, 0

    def complete(self, messages, tools=None, temperature=0.0, response_format=None):
        self.calls += 1
        r = self.replies.pop(0) if self.replies else self.default
        if isinstance(r, Exception):
            raise r
        return Reply(r)


def new_broker():
    b = FakeBroker()
    for t, p in ((INBOX_TOPIC, 1), (TASKS_TOPIC, TASKS_PARTITIONS), (DRAFTS_TOPIC, 1), (FINAL_TOPIC, 1), (DEAD_LETTER_TOPIC, 1)):
        b.create_topic(t, p)
    return b


def consumers(broker):
    return {p: FakeConsumer(broker, t, "eval-" + uuid.uuid4().hex[:6]) for p, t in
            (("plan", TASKS_TOPIC), ("draft", DRAFTS_TOPIC), ("final", FINAL_TOPIC))}


async def main() -> int:
    broker = new_broker()
    tasks = []
    for stage in (make_planner(FAST), make_writer(FAST, "A"), make_reviewer(FAST)):
        c = FakeConsumer(broker, stage.in_topic, stage.group)
        await c.start()
        tasks.append(asyncio.create_task(run_stage(stage, c, FakeProducer(broker), FAST, None, QUIET)))
    client = FakeConsumer(broker, FINAL_TOPIC, "client")
    await client.start()
    cid = str(uuid.uuid4())
    await ask(FakeProducer(broker), client, "What should I do with recalled berries?", cid, "berries-1", 3.0)
    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    # noise on the topics: malformed messages, a duplicate, another request's message
    prod = FakeProducer(broker)
    await prod.send_and_wait(DRAFTS_TOPIC, b"this is not json")
    await prod.send_and_wait(DRAFTS_TOPIC, b"[1,2,3]")
    await prod.send_and_wait(FINAL_TOPIC, json.dumps({"no_correlation": 1}).encode())
    dup = json.loads(broker.all_values(DRAFTS_TOPIC)[0])
    await prod.send_and_wait(DRAFTS_TOPIC, json.dumps(dup).encode())
    other = str(uuid.uuid4())
    await prod.send_and_wait(TASKS_TOPIC, json.dumps({"correlation_id": other, "question": "q", "plan": {"steps": ["a"]}}).encode())

    t0 = time.monotonic()
    got = await collect_many([cid, "no-such-trace"], consumers(broker), timeout_s=0.4)
    b = got["bundles"][cid]
    check("collector: plan, draft and final joined by correlation_id", not b["missing"] and b["trace_id"] == cid)
    check("collector: draft text, plan steps and final answer are the original message content",
          b["draft"] and b["plan"]["steps"] and b["final_answer"] == b["draft"] and b["final_status"] == "approved")
    check("collector: Kafka topic/partition/offset kept for each part", all(
        k in b["kafka"][p] for p in ("plan", "draft", "final") for k in ("topic", "partition", "offset")))
    check("collector: malformed messages are counted and skipped", got["stats"]["malformed"] == 3, str(got["stats"]))
    check("collector: a duplicate message is ignored", got["stats"]["duplicates"] == 1, str(got["stats"]))
    check("collector: an unknown trace_id comes back incomplete, and the scan is bounded",
          got["bundles"]["no-such-trace"]["missing"] == ["plan", "draft", "final"] and time.monotonic() - t0 < 5)
    check("collector: the scan reports it hit the deadline for the missing request", got["stats"]["timed_out"] >= 1)

    path = TMP / "bundles.jsonl"
    save_bundles([b], path)
    check("bundles: save and load round trip", load_bundles(path)[cid] == b)

    # evaluator with a scripted judge: plan 4, draft 3, final 5
    j = OllamaJudge(client=ScriptedClient(['{"score":4,"reason":"plan ok"}', '{"score":3,"reason":"draft ok"}',
                                           '{"score":5,"reason":"final ok"}']))
    r = evaluate_bundle(b, build_metrics(j), "test-judge")
    s = r["scores"]
    check("evaluator: scores on the 1-5 scale with reasons", [s[k]["score"] for k in ("plan_quality", "writer_helpfulness", "final_helpfulness")] == [4, 3, 5]
          and s["writer_helpfulness"]["reason"] == "draft ok")
    check("evaluator: Writer score carries the trace_id; final result carries the final answer",
          r["writer_helpfulness_trace_id"] == cid and r["inputs"]["final_answer"] == b["final_answer"])
    imp = r["improvement"]
    check("improvement: both scores and the difference", (imp["draft_score"], imp["final_score"], imp["difference"]) == (3, 5, 2))
    check("improvement: identical text is flagged and a non-zero difference is called judge noise",
          imp["identical_text"] and "judge noise" in imp["interpretation"])
    check("evaluator: status ok, no errors", r["status"] == "ok" and not r["errors"])
    ev = [x for x in read_spans(TMP / "spans.jsonl") if x["stage"] == "evaluator" and x["trace_id"] == cid]
    check("evaluator: one 'evaluator' span with the same trace_id", len(ev) == 1 and ev[0]["status"] == "ok")
    append_results([r], TMP / "evals.jsonl")
    check("results: append and reload", load_results(TMP / "evals.jsonl")[0]["trace_id"] == cid)

    # judge unavailable: every call times out -> bounded, error recorded, no exception
    bad = OllamaJudge(client=ScriptedClient([TimeoutError("timed out")] * 20), retries=1)
    t0 = time.monotonic()
    r2 = evaluate_bundle(b, build_metrics(bad), "dead-judge")
    check("unavailable judge: all three scores null with the error text, status error, returns quickly",
          r2["status"] == "error" and all(v["score"] is None and "TimeoutError" in v["error"] for v in r2["scores"].values())
          and time.monotonic() - t0 < 5)
    check("unavailable judge: difference is null and the interpretation says so",
          r2["improvement"]["difference"] is None and "not computed" in r2["improvement"]["interpretation"])
    ev2 = [x for x in read_spans(TMP / "spans.jsonl") if x["stage"] == "evaluator" and x["status"] == "error"]
    check("unavailable judge: the evaluator span is status=error", len(ev2) == 1 and "TimeoutError" in ev2[0]["error"])

    # one metric fails, the others still run
    mixed = OllamaJudge(client=ScriptedClient(['{"score":4,"reason":"a"}', "garbage", "garbage", '{"score":2,"reason":"c"}']), retries=1)
    r3 = evaluate_bundle(b, build_metrics(mixed), "mixed")
    check("one failing metric: status partial, the other scores still present",
          r3["status"] == "partial" and r3["scores"]["plan_quality"]["score"] == 4 and r3["scores"]["writer_helpfulness"]["score"] is None
          and r3["scores"]["final_helpfulness"]["score"] == 2)

    # malformed / incomplete bundle: nothing to judge, no judge call
    sc = ScriptedClient([])
    r4 = evaluate_bundle(make_bundle("x", {}), build_metrics(OllamaJudge(client=sc)), "j")
    check("incomplete bundle: no judge calls, status error, missing parts listed",
          sc.calls == 0 and r4["status"] == "error" and r4["missing_parts"] == ["plan", "draft", "final"])

    # case budget
    r5 = evaluate_bundle(b, build_metrics(OllamaJudge(client=ScriptedClient([]))), "j", budget_s=-1)
    check("case time budget: metrics after the budget are skipped with a clear error",
          r5["status"] == "error" and "budget" in r5["scores"]["plan_quality"]["error"])

    check("interpret: higher / lower / equal / rejected / missing", all([
        "higher" in interpret(2, 4, "a", "b", "approved"), "lower" in interpret(4, 2, "a", "b", "approved"),
        "no change" in interpret(3, 3, "a", "b", "approved"), "rejected" in interpret(3, 3, "a", "R", "rejected"),
        "not computed" in interpret(None, 3, "a", "b", "approved")]))
    print(f"\n{passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
