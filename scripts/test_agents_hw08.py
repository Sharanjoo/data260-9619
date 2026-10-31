"""HW8 Part 2/3 offline tests: the three agents, idempotency, commit-after-success, retries + dead-letter and
partition-key ordering, on the in-memory broker. No Docker, no Kafka, no model:  python scripts/test_agents_hw08.py"""
from __future__ import annotations

import asyncio
import json
import sys
import uuid
from dataclasses import replace
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "code"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fake_kafka_hw08 import FakeBroker, FakeConsumer, FakeProducer  # noqa: E402
from kafka_agents.brain import Brain, draft_checks  # noqa: E402
from kafka_agents.runtime import DoneStore, run_stage  # noqa: E402
from kafka_agents.scenarios import ordering_messages, order_violations  # noqa: E402
import kafka_agents.send_question as send_question  # noqa: E402
from kafka_agents.send_question import ask  # noqa: E402
from kafka_agents.settings import (DEAD_LETTER_TOPIC, DRAFTS_TOPIC, FINAL_TOPIC, INBOX_TOPIC, TASKS_PARTITIONS,  # noqa: E402
                                   TASKS_TOPIC, Flags, load_flags)
from kafka_agents.stages import make_planner, make_reviewer, make_writer  # noqa: E402

passed = failed = 0
QUIET = lambda comp, text: None  # noqa: E731


def check(name: str, ok: bool, detail: str = "") -> None:
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
        print(f"  FAIL {name} {detail}")


send_question.log = lambda comp, text: None  # keep the test output quiet
FAST = Flags(mode="fast", retry_backoff_s=0.01)
Q = "I bought recalled frozen berries. What should I do with the bag I have?"


def new_broker() -> FakeBroker:
    b = FakeBroker()
    for t, p in ((INBOX_TOPIC, 1), (TASKS_TOPIC, TASKS_PARTITIONS), (DRAFTS_TOPIC, 1), (FINAL_TOPIC, 1),
                 (DEAD_LETTER_TOPIC, 1)):
        b.create_topic(t, p)
    return b


def agent(broker, stage, flags, partitions=None, done=None, log_fn=QUIET):
    consumer = FakeConsumer(broker, stage.in_topic, stage.group, partitions)
    task = asyncio.create_task(_run(stage, consumer, flags, broker, done, log_fn))
    return consumer, task


async def _run(stage, consumer, flags, broker, done, log_fn):
    await consumer.start()
    await run_stage(stage, consumer, FakeProducer(broker), flags, done, log_fn)


async def settle(broker, topic, n, timeout=3.0):
    loop = asyncio.get_event_loop()
    end = loop.time() + timeout
    while loop.time() < end:
        if len(broker.all_values(topic)) >= n:
            return True
        await asyncio.sleep(0.01)
    return False


def msgs(broker, topic):
    return [json.loads(v) for v in broker.all_values(topic)]


async def stop(*tasks):
    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


async def journey_and_duplicates():
    broker = new_broker()
    log_lines = []
    lg = lambda c, t: log_lines.append((c, t))  # noqa: E731
    _, tp = agent(broker, make_planner(FAST), FAST, log_fn=lg)
    _, tw = agent(broker, make_writer(FAST, "A"), FAST, log_fn=lg)
    _, tr = agent(broker, make_reviewer(FAST), FAST, log_fn=lg)
    client = FakeConsumer(broker, FINAL_TOPIC, "client")
    await client.start()
    cid = str(uuid.uuid4())
    final = await ask(FakeProducer(broker), client, Q, cid, "berries-1", 3.0)
    check("journey: a final message arrives", final is not None)
    check("journey: status approved and answer present", bool(final) and final["status"] == "approved"
          and len(final["answer"]) > 20)
    for topic in (INBOX_TOPIC, TASKS_TOPIC, DRAFTS_TOPIC, FINAL_TOPIC):
        got = msgs(broker, topic)
        check(f"journey: {topic} has exactly one message with the same correlation_id",
              len(got) == 1 and got[0]["correlation_id"] == cid)
    task_rec = broker.topics[TASKS_TOPIC][0] + broker.topics[TASKS_TOPIC][1]
    check("journey: tasks message keyed by entity", task_rec[0].key == b"berries-1")
    check("journey: no dead letters", not broker.all_values(DEAD_LETTER_TOPIC))
    check("journey: stage logs mention the correlation_id", all(
        any(cid in t for c, t in log_lines if c.startswith(s)) for s in ("PLANNER", "WRITER", "REVIEWER")))
    check("journey: offsets committed after success", all(broker.committed.get((g, t, 0)) == 1 for g, t in (
        ("s9619-planner", INBOX_TOPIC), ("s9619-reviewer", DRAFTS_TOPIC))))
    # duplicate delivery: the same question again
    await ask(FakeProducer(broker), client, Q, cid, "berries-1", 0)
    await asyncio.sleep(0.3)
    check("duplicate (idempotent): still 1 task, 1 draft, 1 final",
          [len(msgs(broker, t)) for t in (TASKS_TOPIC, DRAFTS_TOPIC, FINAL_TOPIC)] == [1, 1, 1])
    check("duplicate (idempotent): the skip is logged", any("DUPLICATE" in t for _, t in log_lines))
    await stop(tp, tw, tr)

    broker = new_broker()
    naive = replace(FAST, idempotent=False)
    _, tp = agent(broker, make_planner(naive), naive)
    _, tw = agent(broker, make_writer(naive, "A"), naive)
    _, tr = agent(broker, make_reviewer(naive), naive)
    client = FakeConsumer(broker, FINAL_TOPIC, "client")
    await client.start()
    await ask(FakeProducer(broker), client, Q, cid, None, 3.0)
    await ask(FakeProducer(broker), client, Q, cid, None, 0)
    await settle(broker, FINAL_TOPIC, 2)
    check("duplicate (idempotency off): 2 drafts and 2 finals",
          [len(msgs(broker, t)) for t in (DRAFTS_TOPIC, FINAL_TOPIC)] == [2, 2])
    await stop(tp, tw, tr)


async def kill_mid_processing():
    for mode in ("after", "before"):
        broker = new_broker()
        flags = replace(FAST, write_delay_s=0.4, commit_mode=mode)
        _, tp = agent(broker, make_planner(flags), flags)
        c1, tw1 = agent(broker, make_writer(flags, "A"), flags)
        await ask(FakeProducer(broker), FakeConsumer(broker, FINAL_TOPIC, "c"), Q, "cid-kill", "e1", 0)
        await settle(broker, TASKS_TOPIC, 1)
        await asyncio.sleep(0.15)  # the Writer has the message and is "thinking"
        await stop(tw1)            # kill -9
        check(f"kill ({mode}): nothing was published by the dead Writer", not broker.all_values(DRAFTS_TOPIC))
        committed = sum(v for (g, t, _), v in broker.committed.items() if g == "s9619-writer")
        check(f"kill ({mode}): offset {'NOT ' if mode == 'after' else ''}committed", committed == (0 if mode == "after" else 1))
        _, tw2 = agent(broker, make_writer(flags, "A"), flags)  # restart
        got = await settle(broker, DRAFTS_TOPIC, 1, timeout=1.5)
        if mode == "after":
            check("kill (after): after the restart the same message is redelivered and finished",
                  got and msgs(broker, DRAFTS_TOPIC)[0]["correlation_id"] == "cid-kill")
        else:
            check("kill (before): after the restart the message is gone for good (lost)", not got)
        await stop(tp, tw2)


async def poison():
    bad = {"correlation_id": "cid-bad", "stage": "plan", "question": "q", "plan": "NOT A LIST", "entity_key": "e"}
    good = {"correlation_id": "cid-good", "stage": "plan", "question": "q", "plan": {"steps": ["a", "b"]},
            "entity_key": "e"}
    for limit in (3, 0):
        broker = new_broker()
        flags = replace(FAST, max_attempts=limit)
        lines = []
        _, tw = agent(broker, make_writer(flags, "A"), flags, log_fn=lambda c, t: lines.append(t))
        prod = FakeProducer(broker)
        await prod.send_and_wait(TASKS_TOPIC, json.dumps(bad).encode())
        await prod.send_and_wait(TASKS_TOPIC, json.dumps(good).encode())
        if limit:
            ok = await settle(broker, DRAFTS_TOPIC, 1)
            dead = msgs(broker, DEAD_LETTER_TOPIC)
            check("poison (limit 3): exactly 3 attempts logged", sum("failed correlation_id=cid-bad" in t for t in lines) == 3)
            check("poison (limit 3): bad message on the dead-letter topic", len(dead) == 1
                  and dead[0]["correlation_id"] == "cid-bad" and dead[0]["attempts"] == 3)
            check("poison (limit 3): the later message was still processed", ok
                  and msgs(broker, DRAFTS_TOPIC)[0]["correlation_id"] == "cid-good")
        else:
            await asyncio.sleep(0.4)
            check("poison (no limit): the bad message is retried again and again", sum(
                "failed correlation_id=cid-bad" in t for t in lines) > 10)
            check("poison (no limit): the later message is blocked, nothing in dead-letter",
                  not broker.all_values(DRAFTS_TOPIC) and not broker.all_values(DEAD_LETTER_TOPIC))
        await stop(tw)
    broker = new_broker()  # a message that is not even JSON
    _, tw = agent(broker, make_writer(FAST, "A"), FAST)
    prod = FakeProducer(broker)
    await prod.send_and_wait(TASKS_TOPIC, b"{not json")
    await prod.send_and_wait(TASKS_TOPIC, json.dumps(good).encode())
    ok = await settle(broker, DRAFTS_TOPIC, 1)
    check("poison: unreadable bytes go to dead-letter and the next message is processed",
          ok and len(msgs(broker, DEAD_LETTER_TOPIC)) == 1)
    await stop(tw)


async def ordering():
    results = {}
    for task_key in ("none", "entity"):
        broker = new_broker()
        flags = replace(FAST, task_key=task_key, jitter_s=0.25)
        tasks = [agent(broker, make_writer(flags, n), flags, partitions=[i])[1] for i, n in enumerate("AB")]
        prod = FakeProducer(broker)
        for m in ordering_messages():
            key = m["entity_key"].encode() if task_key == "entity" else None
            await prod.send_and_wait(TASKS_TOPIC, json.dumps(m).encode(), key=key)
        ok = await settle(broker, DRAFTS_TOPIC, 20, timeout=8)
        res = order_violations(msgs(broker, DRAFTS_TOPIC))
        results[task_key] = res["total_out_of_order_pairs"]
        check(f"ordering ({task_key}): all 20 messages processed", ok)
        if task_key == "entity":
            parts = {}
            for p, part in enumerate(broker.topics[TASKS_TOPIC]):
                for r in part:
                    parts.setdefault(json.loads(r.value)["entity_key"], set()).add(p)
            check("ordering (entity key): every entity's messages sit in ONE partition",
                  all(len(v) == 1 for v in parts.values()))
        await stop(*tasks)
    check("ordering: without a key related messages finish out of order", results["none"] > 0, str(results))
    check("ordering: with the entity key they finish in order", results["entity"] == 0, str(results))
    check("ordering messages: same seed, same list", ordering_messages() == ordering_messages())
    check("ordering messages: 20 messages, an entity has several", len(ordering_messages()) == 20
          and max(sum(m["entity_key"] == e for m in ordering_messages()) for e in {m["entity_key"] for m in ordering_messages()}) > 1)


def plain():
    check("flags: defaults", load_flags({}) == Flags())
    f = load_flags({"HW8_IDEMPOTENT": "0", "HW8_COMMIT_MODE": "before", "HW8_MAX_ATTEMPTS": "0", "HW8_TASK_KEY": "none"})
    check("flags: environment switches", not f.idempotent and f.commit_mode == "before" and f.max_attempts == 0
          and f.task_key == "none")
    check("draft checks: a url fails", not draft_checks("see https://example.com for the refund of the product now")["no_url_or_phone_number"])
    check("draft checks: a phone number fails", not draft_checks("call 555-123-4567 to get your refund today ok")["no_url_or_phone_number"])
    check("draft checks: normal text passes", all(draft_checks("Do not eat the product; return it to the store.").values()))
    try:
        Brain("bogus")
        check("brain rejects an unknown mode", False)
    except ValueError:
        check("brain rejects an unknown mode", True)
    d = DoneStore()
    d.add("x")
    check("done store remembers", "x" in d and "y" not in d)
    import tempfile
    path = str(Path(tempfile.mkdtemp()) / "s" / "w.txt")
    DoneStore(path).add("abc")
    check("done store survives a restart when it has a file", "abc" in DoneStore(path))


async def main():
    plain()
    await journey_and_duplicates()
    await kill_mid_processing()
    await poison()
    await ordering()


asyncio.run(main())
print(f"{passed} checks passed, {failed} failed")
sys.exit(1 if failed else 0)
