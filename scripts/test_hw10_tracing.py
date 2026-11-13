"""HW10 Part 4.1 offline checks: spans carry the HW8 correlation_id through cache lookup, inbox, tasks, drafts and final,
on the in-memory broker with stand-ins for Redis and the model (python scripts/test_hw10_tracing.py).

Proves: one trace_id on every span; a hit has cache_lookup + request only; a miss has cache_lookup, queue waits, planner,
writer, reviewer and request; a failing stage writes status=error spans with the error text; tracing never raises."""
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

TMP = Path(tempfile.mkdtemp(prefix="hw10_trace_"))
SPANS = TMP / "spans.jsonl"
os.environ["HW10_SPANS_PATH"] = str(SPANS)

from cache_layer.ingress import SemanticIngress  # noqa: E402
from fake_kafka_hw08 import FakeBroker, FakeConsumer, FakeProducer  # noqa: E402
from kafka_agents.runtime import run_stage  # noqa: E402
from kafka_agents.send_question import ask  # noqa: E402
from kafka_agents.settings import (DEAD_LETTER_TOPIC, DRAFTS_TOPIC, FINAL_TOPIC, INBOX_TOPIC, TASKS_PARTITIONS,  # noqa: E402
                                   TASKS_TOPIC, Flags)
from kafka_agents.stages import make_planner, make_reviewer, make_writer  # noqa: E402
from test_hw9_cache import REC, FakeCache, FakeEmbedder, FakeFacts, unit  # noqa: E402
from tracing.spans import emit, read_spans, span, spans_path  # noqa: E402
from cache_layer.questions import units_question  # noqa: E402

passed = failed = 0
FAST = Flags(mode="fast", retry_backoff_s=0.01)
QUIET = lambda comp, text: None  # noqa: E731


def check(name: str, ok: bool, detail: str = "") -> None:
    global passed, failed
    passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))


def new_broker() -> FakeBroker:
    b = FakeBroker()
    for t, p in ((INBOX_TOPIC, 1), (TASKS_TOPIC, TASKS_PARTITIONS), (DRAFTS_TOPIC, 1), (FINAL_TOPIC, 1),
                 (DEAD_LETTER_TOPIC, 1)):
        b.create_topic(t, p)
    return b


async def stop(*tasks):
    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


def spans_for(tid: str) -> list:
    return [s for s in read_spans(SPANS) if s["trace_id"] == tid]


class BrokerAgent:
    """Same job as cache_layer.agent_client.AgentClient, on the in-memory broker."""

    def __init__(self, broker) -> None:
        self.broker = broker
        self.consumer = FakeConsumer(broker, FINAL_TOPIC, "client-" + uuid.uuid4().hex[:6])

    async def run(self, question, correlation_id, entity_key=None):
        await self.consumer.start()
        return await ask(FakeProducer(self.broker), self.consumer, question, correlation_id, entity_key, 3.0)


async def start_agents(broker, flags=FAST):
    tasks = []
    for stage in (make_planner(flags), make_writer(flags, "A"), make_reviewer(flags)):
        consumer = FakeConsumer(broker, stage.in_topic, stage.group)
        await consumer.start()
        tasks.append(asyncio.create_task(run_stage(stage, consumer, FakeProducer(broker), flags, None, QUIET)))
    return tasks


async def main() -> int:
    broker = new_broker()
    broker._clock = int(time.time() * 1000)  # real-looking epoch milliseconds, as a real broker stamps records
    tasks = await start_agents(broker)
    q = units_question(REC)
    q_other = "How do I find out whether my store sells a recalled product?"
    table = {q: unit(1, 0, 0), q_other: unit(0, 1, 0)}
    ing = SemanticIngress(FakeCache(), FakeEmbedder(table), FakeFacts({REC["record_code"]: dict(REC)}),
                          BrokerAgent(broker), threshold=0.9)

    miss = await ing.answer(q)
    tid = miss["trace_id"]
    check("miss: result carries trace_id == correlation_id", tid == miss["correlation_id"] and not miss["is_cached"])
    got = spans_for(tid)
    stages = [s["stage"] for s in got]
    for needed in ("cache_lookup", "queue_wait_inbox", "planner", "queue_wait_tasks", "writer", "queue_wait_drafts",
                   "reviewer", "queue_wait_final", "agent_pipeline", "request"):
        check(f"miss: span {needed} present with the same trace_id", needed in stages, str(stages))
    msgs = [json.loads(v) for t in (TASKS_TOPIC, FINAL_TOPIC) for v in broker.all_values(t)]
    check("miss: the messages on Kafka carry that same id (no second request id)",
          all(m["correlation_id"] == tid for m in msgs) and len(msgs) == 2)
    check("miss: every span has trace_id, stage, start, end, status", all(
        all(k in s for k in ("trace_id", "stage", "start", "end", "status", "error")) for s in got))
    check("miss: every span status is ok and error is null", all(s["status"] == "ok" and s["error"] is None for s in got))
    check("miss: durations are non-negative and request >= agent_pipeline >= writer", all(s["duration_ms"] >= 0 for s in got)
          and max(s["duration_ms"] for s in got if s["stage"] == "request")
          >= max(s["duration_ms"] for s in got if s["stage"] == "agent_pipeline"))
    lookup = next(s for s in got if s["stage"] == "cache_lookup")
    check("miss: cache_lookup span says hit=false and has the similarity", lookup["attrs"]["hit"] is False
          and "similarity" in lookup["attrs"])

    hit = await ing.answer(q)
    h = spans_for(hit["trace_id"])
    check("hit: result is cached and has its own trace_id", hit["is_cached"] and hit["trace_id"] != tid)
    check("hit: only cache_lookup + request spans (no agent stages)", sorted(s["stage"] for s in h) == ["cache_lookup", "request"])
    check("hit: cache_lookup span says hit=true", next(s for s in h if s["stage"] == "cache_lookup")["attrs"]["hit"] is True)

    # failure: a plan with no steps makes the Writer fail on every attempt, then dead-letter
    bad_cid = str(uuid.uuid4())
    await FakeProducer(broker).send_and_wait(
        TASKS_TOPIC, json.dumps({"correlation_id": bad_cid, "stage": "plan", "question": "x", "plan": {"steps": []}}).encode())
    for _ in range(300):
        if broker.all_values(DEAD_LETTER_TOPIC):
            break
        await asyncio.sleep(0.01)
    bad = spans_for(bad_cid)
    errs = [s for s in bad if s["stage"] == "writer" and s["status"] == "error"]
    check("failed trace: three writer spans with status=error (max_attempts=3)", len(errs) == 3, str([s["stage"] for s in bad]))
    check("failed trace: the error names the cause", bool(errs) and "plan.steps" in errs[0]["error"], errs[0]["error"] if errs else "")
    dl = [s for s in bad if s["stage"] == "dead_letter"]
    check("failed trace: a dead_letter span names the failing stage and the error", len(dl) == 1
          and dl[0]["attrs"]["failed_stage"] == "writer" and "plan.steps" in dl[0]["error"], str(dl[:1]))
    check("failed trace: attempts are numbered 1..3", sorted(s["attrs"]["attempt"] for s in errs) == [1, 2, 3])
    await stop(*tasks)

    # helper behaviour
    t0 = time.time() * 1000
    r = emit("t1", "unit", t0, t0 + 5.0)
    check("emit: returns the record with duration 5 ms", r is not None and abs(r["duration_ms"] - 5.0) < 1e-6)
    try:
        with span("t2", "boom"):
            raise ValueError("bad thing")
    except ValueError:
        pass
    s2 = spans_for("t2")
    check("span(): an exception becomes status=error with the text, and is re-raised", len(s2) == 1
          and s2[0]["status"] == "error" and "ValueError: bad thing" in s2[0]["error"])
    os.environ["HW10_SPANS_PATH"] = str(TMP)  # a directory: cannot be opened as a file
    check("emit: a write failure never raises", emit("t3", "x", 1.0, 2.0) is None)
    os.environ["HW10_SPANS_PATH"] = str(SPANS)
    os.environ["HW10_TRACE_OFF"] = "1"
    check("tracing can be switched off", spans_path() is None and emit("t4", "x", 1.0, 2.0) is None)
    del os.environ["HW10_TRACE_OFF"]
    check("emit without a trace_id writes nothing", emit(None, "x", 1.0, 2.0) is None)
    print(f"\n{passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
