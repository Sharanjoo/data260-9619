"""HW8 Part 1 offline tests: validation, the worker's request handling, the Kafka round trip (in-memory broker)
and the FastAPI wrapper. No Docker and no Kafka needed:  python scripts/test_kafka_hw08.py"""
from __future__ import annotations

import asyncio
import json
import sys
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "code"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import httpx  # noqa: E402
from fake_kafka_hw08 import FakeBroker, FakeConsumer, FakeProducer  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from kafka_api import server  # noqa: E402
from kafka_api.config import REQUEST_TOPIC, RESPONSE_TOPIC, WORKER_GROUP, API_GROUP  # noqa: E402
from kafka_api.entity_logic import RecallNoticeStore, validate_recall_notice  # noqa: E402
from kafka_api.rpc import KafkaRPC, KafkaUnavailable  # noqa: E402
from kafka_api.healthcheck import healthy  # noqa: E402
from kafka_api.worker import heartbeat, run_worker  # noqa: E402

passed = failed = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
        print(f"  FAIL {name} {detail}")


GOOD = {"productName": "Frozen Mixed Berries", "brandName": "Northfield Farms",
        "submitterEmail": "safety@northfield.example",
        "description": "Possible Hepatitis A contamination found in one lot.",
        "category": "food-safety-recall", "termsAccepted": True}


def without(key):
    return {k: v for k, v in GOOD.items() if k != key}


def quiet(*_a):
    return None


# ---------------------------------------------------------------- validation
clean, err = validate_recall_notice(GOOD)
check("valid notice accepted", err is None and clean["productName"] == "Frozen Mixed Berries")
for key in GOOD:
    _, err = validate_recall_notice(without(key))
    check(f"missing {key} rejected", err is not None and key in err, str(err))
for key in ("productName", "brandName", "submitterEmail", "description"):
    _, err = validate_recall_notice({**GOOD, key: "   "})
    check(f"empty {key} rejected", err is not None and "empty" in err, str(err))
    _, err = validate_recall_notice({**GOOD, key: 123})
    check(f"non-text {key} rejected", err is not None, str(err))
check("bad email rejected", validate_recall_notice({**GOOD, "submitterEmail": "nobody"})[1] is not None)
check("25-character description rejected", validate_recall_notice({**GOOD, "description": "x" * 25})[1] is not None)
check("26-character description accepted", validate_recall_notice({**GOOD, "description": "x" * 26})[1] is None)
check("bad category rejected", validate_recall_notice({**GOOD, "category": "other"})[1] is not None)
check("termsAccepted false rejected", validate_recall_notice({**GOOD, "termsAccepted": False})[1] is not None)
check("termsAccepted text rejected", validate_recall_notice({**GOOD, "termsAccepted": "true"})[1] is not None)
check("unknown field rejected", validate_recall_notice({**GOOD, "colour": "red"})[1] is not None)
check("non-object data rejected", validate_recall_notice(["x"])[1] is not None)
check("too long name rejected", validate_recall_notice({**GOOD, "productName": "x" * 101})[1] is not None)

# ---------------------------------------------------------------- store (the worker's business logic)
store = RecallNoticeStore()
r = store.handle({"correlation_id": "c1", "operation": "CREATE_RECALL_NOTICE", "data": GOOD})
check("create succeeds", r["success"] is True and r["message"] == "Recall notice created", str(r))
check("create echoes correlation_id", r["correlation_id"] == "c1")
check("id is a UUID", bool(uuid.UUID(r["recall_notice_id"])))
g = store.handle({"correlation_id": "c2", "operation": "GET_RECALL_NOTICE", "data": {"recall_notice_id": r["recall_notice_id"]}})
check("get returns the entity", g["success"] is True and g["recall_notice"]["recall_notice_id"] == r["recall_notice_id"]
      and g["recall_notice"]["productName"] == GOOD["productName"] and "submissionDate" in g["recall_notice"], str(g))
check("get echoes correlation_id", g["correlation_id"] == "c2")
n = store.handle({"correlation_id": "c3", "operation": "GET_RECALL_NOTICE", "data": {"recall_notice_id": "nope"}})
check("unknown id -> not found", n == {"correlation_id": "c3", "success": False, "error": "Recall notice not found"}, str(n))
m = store.handle({"correlation_id": "c4", "operation": "GET_RECALL_NOTICE", "data": {}})
check("missing id -> error with correlation_id", m["success"] is False and m["correlation_id"] == "c4")
u = store.handle({"correlation_id": "c5", "operation": "DELETE_RECALL_NOTICE", "data": {}})
check("unknown operation", u == {"correlation_id": "c5", "success": False, "error": "Unknown operation"}, str(u))
bad = store.handle({"correlation_id": "c6", "operation": "CREATE_RECALL_NOTICE", "data": without("category")})
check("invalid create -> error with correlation_id", bad["success"] is False and bad["correlation_id"] == "c6")
check("invalid create stored nothing", len(store.notices) == 1)
nc = store.handle({"operation": "CREATE_RECALL_NOTICE", "data": GOOD})
check("missing correlation_id rejected", nc["success"] is False and nc["correlation_id"] is None)
check("non-object request rejected", store.handle("hello")["success"] is False)
d1 = store.handle({"correlation_id": "dup", "operation": "CREATE_RECALL_NOTICE", "data": GOOD})
d2 = store.handle({"correlation_id": "dup", "operation": "CREATE_RECALL_NOTICE", "data": GOOD})
check("duplicate correlation_id returns the same response", d1 == d2)
check("duplicate created nothing new", len(store.notices) == 2 and store.duplicates_ignored == 1)
loose = RecallNoticeStore(idempotent=False)
loose.handle({"correlation_id": "dup", "operation": "CREATE_RECALL_NOTICE", "data": GOOD})
loose.handle({"correlation_id": "dup", "operation": "CREATE_RECALL_NOTICE", "data": GOOD})
check("without idempotency a replay creates a second notice", len(loose.notices) == 2)


# ---------------------------------------------------------------- Kafka round trip on the in-memory broker
async def round_trip() -> None:
    broker = FakeBroker()
    broker.create_topic(REQUEST_TOPIC)
    broker.create_topic(RESPONSE_TOPIC)
    w_consumer = FakeConsumer(broker, REQUEST_TOPIC, WORKER_GROUP)
    w_producer = FakeProducer(broker)
    await w_consumer.start()
    worker_store = RecallNoticeStore()
    lines = []
    worker = asyncio.create_task(run_worker(w_consumer, w_producer, worker_store, lambda c, t: lines.append((c, t))))
    rpc = KafkaRPC(timeout=2.0, log_fn=quiet,
                   producer_factory=lambda: FakeProducer(broker),
                   consumer_factory=lambda: FakeConsumer(broker, RESPONSE_TOPIC, API_GROUP))
    await rpc.start()
    await asyncio.sleep(0.05)
    check("worker prints the ready line", ("WORKER", "Consumer is ready and listening...") in lines)

    cid = str(uuid.uuid4())
    created = await rpc.request("CREATE_RECALL_NOTICE", GOOD, cid)
    check("rpc create works", created["success"] is True and created["correlation_id"] == cid, str(created))
    req = json.loads(broker.topics[REQUEST_TOPIC][0][0].value)
    check("request message has correlation_id, reply_to, operation, data",
          set(req) == {"correlation_id", "reply_to", "operation", "data"} and req["correlation_id"] == cid
          and req["reply_to"] == RESPONSE_TOPIC and req["operation"] == "CREATE_RECALL_NOTICE")
    resp = json.loads(broker.topics[RESPONSE_TOPIC][0][0].value)
    check("response on the response topic keeps the correlation_id", resp["correlation_id"] == cid)
    cid2 = str(uuid.uuid4())
    got = await rpc.request("GET_RECALL_NOTICE", {"recall_notice_id": created["recall_notice_id"]}, cid2)
    check("rpc get round-trips the entity", got["success"] and got["recall_notice"]["brandName"] == "Northfield Farms"
          and got["correlation_id"] == cid2, str(got))
    nf = await rpc.request("GET_RECALL_NOTICE", {"recall_notice_id": "missing"}, "cid-nf")
    check("rpc not found keeps the correlation_id", nf["success"] is False and nf["correlation_id"] == "cid-nf")
    un = await rpc.request("EXPLODE", {}, "cid-un")
    check("rpc unknown operation", un["error"] == "Unknown operation" and un["correlation_id"] == "cid-un")
    auto = await rpc.request("GET_RECALL_NOTICE", {"recall_notice_id": "x"})
    check("rpc creates a correlation_id when none is given", bool(uuid.UUID(auto["correlation_id"])))
    check("offsets are committed after processing", w_consumer.commits == w_consumer.delivered == 5,
          f"commits={w_consumer.commits} delivered={w_consumer.delivered}")
    check("pending map is empty afterwards", rpc.pending == {})

    # two requests in flight at once get their own answers
    a, b = await asyncio.gather(
        rpc.request("GET_RECALL_NOTICE", {"recall_notice_id": created["recall_notice_id"]}, "cid-a"),
        rpc.request("GET_RECALL_NOTICE", {"recall_notice_id": "zzz"}, "cid-b"))
    check("concurrent requests are matched by correlation_id", a["success"] and not b["success"]
          and a["correlation_id"] == "cid-a" and b["correlation_id"] == "cid-b")

    # a replayed message (same correlation_id delivered twice) creates nothing new
    before = len(worker_store.notices)
    replay = json.dumps({"correlation_id": "replay-1", "reply_to": RESPONSE_TOPIC, "operation": "CREATE_RECALL_NOTICE",
                         "data": GOOD}).encode()
    for _ in range(2):
        broker.produce(REQUEST_TOPIC, replay)
    await asyncio.sleep(0.2)
    check("replayed create stored exactly one notice", len(worker_store.notices) == before + 1)

    # junk and a forbidden reply_to
    broker.produce(REQUEST_TOPIC, b"not json at all")
    broker.produce(REQUEST_TOPIC, json.dumps({"correlation_id": "evil", "reply_to": "some_other_topic",
                                              "operation": "GET_RECALL_NOTICE", "data": {}}).encode())
    await asyncio.sleep(0.2)
    check("worker survives junk and keeps committing", not worker.done() and w_consumer.commits == w_consumer.delivered)
    check("forbidden reply_to is answered on the response topic, not the named topic",
          "some_other_topic" not in broker.topics and any(b'"evil"' in v and b"not allowed" in v
                                                          for v in broker.all_values(RESPONSE_TOPIC)))

    # nobody answering -> timeout, not a hang
    broker2 = FakeBroker()
    lonely = KafkaRPC(timeout=0.3, log_fn=quiet, producer_factory=lambda: FakeProducer(broker2),
                      consumer_factory=lambda: FakeConsumer(broker2, RESPONSE_TOPIC, "g"))
    await lonely.start()
    t = await lonely.request("GET_RECALL_NOTICE", {"recall_notice_id": "x"}, "cid-timeout")
    check("no worker -> clean timeout error with correlation_id",
          t["success"] is False and t["correlation_id"] == "cid-timeout" and t["error"].startswith("Timeout"))
    check("timeout cleans the pending map", lonely.pending == {})
    await lonely.stop()

    # the FastAPI wrapper on top of the same rpc
    server.rpc = rpc
    app = FastAPI()
    app.include_router(server.router)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r1 = await client.post("/api/hw8/recall-notices", json=GOOD)
        check("POST /recall-notices -> 201", r1.status_code == 201 and r1.json()["success"] is True, r1.text)
        nid = r1.json()["recall_notice_id"]
        r2 = await client.get(f"/api/hw8/recall-notices/{nid}")
        check("GET /recall-notices/{id} -> 200", r2.status_code == 200 and r2.json()["recall_notice"]["recall_notice_id"] == nid)
        r3 = await client.get("/api/hw8/recall-notices/unknown")
        check("GET unknown id -> 404", r3.status_code == 404 and r3.json()["success"] is False)
        r4 = await client.post("/api/hw8/recall-notices", json={**GOOD, "category": "nope"})
        check("invalid create -> 422", r4.status_code == 422 and "category" in r4.json()["error"])
        r5 = await client.post("/api/hw8/requests", json={"operation": "CREATE_RECALL_NOTICE", "data": GOOD,
                                                          "correlation_id": "from-client-1"})
        check("generic request keeps the caller's correlation_id", r5.json()["correlation_id"] == "from-client-1")
        r6 = await client.post("/api/hw8/requests", json={"data": {}})
        check("missing operation -> 422", r6.status_code == 422)
        r7 = await client.post("/api/hw8/direct", json={"operation": "CREATE_RECALL_NOTICE", "data": GOOD})
        check("direct endpoint works without Kafka", r7.status_code == 201 and r7.json()["success"] is True, r7.text)
        r8 = await client.get("/api/hw8/health")
        check("health reports the Kafka client", r8.json()["kafka_client_ready"] is True)
        # Kafka down -> 503, not a crash
        down = KafkaRPC(log_fn=quiet, producer_factory=lambda: _Dead(), consumer_factory=lambda: _Dead())
        server.rpc = down
        r9 = await client.post("/api/hw8/recall-notices", json=GOOD)
        check("Kafka down -> 503", r9.status_code == 503 and r9.json()["success"] is False, r9.text)
    try:
        await down.request("GET_RECALL_NOTICE", {})
        check("down rpc raises KafkaUnavailable", False)
    except KafkaUnavailable:
        check("down rpc raises KafkaUnavailable", True)

    await rpc.stop()
    await w_consumer.stop()
    await asyncio.wait_for(worker, 2)


class _Dead:
    async def start(self):
        raise ConnectionError("broker down")

    async def stop(self):
        return None


async def heartbeat_check() -> None:
    import os
    import tempfile
    import time
    path = os.path.join(tempfile.mkdtemp(), "alive")
    check("health check fails when there is no heartbeat file", healthy(path) is False)
    task = asyncio.create_task(heartbeat(path, every=0.05))
    await asyncio.sleep(0.2)
    check("health check passes while the worker beats", healthy(path) is True)
    task.cancel()
    check("health check fails when the heartbeat is old", healthy(path, now=time.time() + 60) is False)


asyncio.run(round_trip())
asyncio.run(heartbeat_check())
print(f"{passed} checks passed, {failed} failed")
sys.exit(1 if failed else 0)
