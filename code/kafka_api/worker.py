"""HW8 Part 1 - the worker: reads requests from s9619_entity_requests, answers on the reply_to topic.

Run it in Docker (compose service `worker`) or by hand from the repo root:
    python code/kafka_api/worker.py

The loop commits the Kafka offset only AFTER the response has been sent, so a worker that dies
mid-request gets the same message again after a restart (at-least-once). The store answers a repeated
correlation_id with the stored response, so the second delivery creates nothing new.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Callable

if __package__ in (None, ""):  # `python code/kafka_api/worker.py` from the repo root
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    __package__ = "kafka_api"

from .healthcheck import HEARTBEAT_FILE  # noqa: E402
from .config import BOOTSTRAP_SERVERS, REQUEST_TOPIC, RESPONSE_TOPIC, WORKER_GROUP  # noqa: E402
from .entity_logic import RecallNoticeStore  # noqa: E402
from .logutil import log  # noqa: E402

ALLOWED_REPLY_TOPICS = (RESPONSE_TOPIC,)


def _dump(obj: Any) -> str:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)


async def handle_message(msg: Any, consumer: Any, producer: Any, store: RecallNoticeStore,
                         log_fn: Callable[[str, str], None] = log) -> None:
    """One request: log it, process it, send the response, then (and only then) commit the offset."""
    where = f"topic={msg.topic} partition={msg.partition} offset={msg.offset}"
    try:
        payload = json.loads(msg.value.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        log_fn("WORKER", f"received {where} unreadable (not JSON): skipped, offset committed")
        await consumer.commit()
        return
    log_fn("WORKER", f"received {where} message={_dump(payload)}")
    if not isinstance(payload, dict):
        log_fn("WORKER", f"{where} is not a JSON object: skipped, offset committed")
        await consumer.commit()
        return
    cid = payload.get("correlation_id")
    reply_to = payload.get("reply_to")
    duplicate = store.idempotent and isinstance(cid, str) and cid in store.answered
    log_fn("WORKER", f"processing operation={payload.get('operation')} correlation_id={cid} reply_to={reply_to}"
                     + ("  (DUPLICATE correlation_id: returning the stored response, nothing new is created)"
                        if duplicate else ""))
    response = store.handle(payload)
    topic = reply_to
    if reply_to not in ALLOWED_REPLY_TOPICS:
        # never publish to a topic named by the request; answer on the response topic instead
        topic = RESPONSE_TOPIC
        response = {"correlation_id": cid, "success": False, "error": "reply_to topic is not allowed"}
    meta = await producer.send_and_wait(topic, _dump(response).encode("utf-8"))
    log_fn("WORKER", f"sent response topic={meta.topic} partition={meta.partition} offset={meta.offset} "
                     f"correlation_id={cid} success={response.get('success')} message={_dump(response)}")
    await consumer.commit()  # only now: the request is fully processed


async def heartbeat(path: str = HEARTBEAT_FILE, every: float = 5.0) -> None:
    """Touch a file every few seconds; the Docker health check (healthcheck.py) looks at its age."""
    while True:
        try:
            Path(path).touch()
        except OSError:
            pass
        await asyncio.sleep(every)


async def run_worker(consumer: Any, producer: Any, store: RecallNoticeStore,
                     log_fn: Callable[[str, str], None] = log) -> None:
    log_fn("WORKER", "Consumer is ready and listening...")
    log_fn("WORKER", f"topic={REQUEST_TOPIC} group={WORKER_GROUP} replies to {RESPONSE_TOPIC}")
    async for msg in consumer:
        await handle_message(msg, consumer, producer, store, log_fn)


async def main() -> None:
    from aiokafka import AIOKafkaConsumer, AIOKafkaProducer  # imported late so the tests need no Kafka client

    store = RecallNoticeStore(idempotent=True)
    for attempt in range(1, 61):
        consumer = AIOKafkaConsumer(
            REQUEST_TOPIC, bootstrap_servers=BOOTSTRAP_SERVERS, group_id=WORKER_GROUP,
            auto_offset_reset="earliest", enable_auto_commit=False)
        producer = AIOKafkaProducer(bootstrap_servers=BOOTSTRAP_SERVERS)
        try:
            await consumer.start()
            await producer.start()
            break
        except Exception as exc:  # noqa: BLE001 - Kafka may still be starting
            log("WORKER", f"Kafka not ready (attempt {attempt}/60): {exc}")
            for closer in (consumer.stop, producer.stop):
                try:
                    await closer()
                except Exception:  # noqa: BLE001
                    pass
            await asyncio.sleep(3)
    else:
        raise SystemExit("worker: could not reach Kafka")
    beat = asyncio.create_task(heartbeat())
    try:
        await run_worker(consumer, producer, store)
    finally:
        beat.cancel()
        await consumer.stop()
        await producer.stop()


if __name__ == "__main__":
    asyncio.run(main())
