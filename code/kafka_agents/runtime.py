"""HW8 Part 2/3 - the loop every agent runs: read a message, do the work, publish, THEN commit the offset.

Protections (each can be switched off with settings.Flags to produce the Part 3 'before' evidence):
  * commit after success   the offset moves only once the result is on the next topic, so a Writer killed
                           mid-work gets the same message again after it restarts (at-least-once delivery)
  * idempotency            a correlation_id that was already processed is skipped, so a duplicate or a redelivery
                           adds no second draft / final answer
  * bounded retries + DLQ  a message that keeps failing is tried max_attempts times, then moved to
                           s9619_dead_letter and the offset is committed, so later messages are not blocked
  * partition key          the planner keys tasks by entity so related messages share a partition (kept in order)
"""
from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional

from kafka_api.config import BOOTSTRAP_SERVERS
from kafka_api.logutil import log
from kafka_agents.settings import BANNER, DEAD_LETTER_TOPIC, Flags
from tracing.spans import emit as trace_emit, now_ms

Handler = Callable[[Dict[str, Any]], Awaitable[List[Dict[str, Any]]]]


def dump(obj: Any) -> str:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)


@dataclass
class Stage:
    name: str                    # PLANNER / WRITER / REVIEWER
    label: str                   # shown in every log line, e.g. WRITER-A
    in_topic: str
    group: str
    out_topic: str
    handler: Handler             # payload -> list of outgoing messages (normally one)
    keyed: bool = False          # use outgoing["entity_key"] as the Kafka key (when flags.task_key == "entity")


class DoneStore:
    """Correlation ids this stage has already finished. Optionally mirrored to a file so a restart remembers them."""

    def __init__(self, path: Optional[str] = None) -> None:
        self.ids: set = set()
        self.path = path
        if path and os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                self.ids = {line.strip() for line in fh if line.strip()}

    def __contains__(self, cid: object) -> bool:
        return cid in self.ids

    def add(self, cid: str) -> None:
        self.ids.add(cid)
        if self.path:
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(cid + "\n")


def _parse(msg: Any) -> Dict[str, Any]:
    try:
        payload = json.loads(msg.value.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError(f"message is not valid JSON ({exc.__class__.__name__})") from None
    if not isinstance(payload, dict):
        raise ValueError("message is not a JSON object")
    return payload


async def process_message(stage: Stage, msg: Any, consumer: Any, producer: Any, done: DoneStore, flags: Flags,
                          log_fn: Callable[[str, str], None] = log) -> None:
    where = f"topic={msg.topic} partition={msg.partition} offset={msg.offset}"
    raw = msg.value.decode("utf-8", "replace")
    key = msg.key.decode("utf-8", "replace") if getattr(msg, "key", None) else None
    log_fn(stage.label, f"received {where}" + (f" key={key}" if key else "") + f" message={raw}")
    if flags.commit_mode == "before":
        await consumer.commit()  # naive: the offset moves before the work is finished
        log_fn(stage.label, f"offset committed BEFORE processing ({where})")

    cid: Optional[str] = None
    attempt = 0
    outs: Optional[List[Dict[str, Any]]] = None
    error = ""
    while True:
        attempt += 1
        try:
            payload = _parse(msg)
            cid = payload.get("correlation_id") if isinstance(payload.get("correlation_id"), str) else None
            if flags.idempotent and cid is not None and cid in done:
                log_fn(stage.label, f"DUPLICATE correlation_id={cid}: already processed, skipped, nothing is "
                                    f"sent again")
                if flags.commit_mode == "after":
                    await consumer.commit()
                return
            if attempt == 1:
                log_fn(stage.label, f"processing correlation_id={cid}")
            handler_start = now_ms()
            sent_ms = getattr(msg, "timestamp", 0) or 0
            if attempt == 1 and sent_ms > 1e12:  # HW10: time the message waited in Kafka before this stage began
                trace_emit(cid, f"queue_wait_{msg.topic.split('_', 1)[-1]}", float(sent_ms), handler_start,
                           topic=msg.topic, partition=msg.partition, offset=msg.offset, consumer=stage.label)
            try:
                outs = await stage.handler(payload)
            except Exception as handler_exc:  # noqa: BLE001 - HW10: record the failing attempt, then re-raise
                trace_emit(cid, stage.name.lower(), handler_start, now_ms(), "error",
                           f"{type(handler_exc).__name__}: {handler_exc}", attempt=attempt, instance=stage.label)
                raise
            trace_emit(cid, stage.name.lower(), handler_start, now_ms(), attempt=attempt, instance=stage.label)
            break
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - any failure of one message must not stop the agent
            error = f"{type(exc).__name__}: {exc}"
            limit = flags.max_attempts
            log_fn(stage.label, f"attempt {attempt}/{limit if limit else 'unlimited'} failed "
                                f"correlation_id={cid}: {error}")
            if limit and attempt >= limit:
                break
            await asyncio.sleep(flags.retry_backoff_s)

    if outs is None:  # gave up: park the message on the dead-letter topic and move on
        dead = {"stage": stage.name, "correlation_id": cid, "attempts": attempt, "error": error,
                "source": {"topic": msg.topic, "partition": msg.partition, "offset": msg.offset}, "original": raw}
        dl_start = now_ms()
        meta = await producer.send_and_wait(DEAD_LETTER_TOPIC, dump(dead).encode("utf-8"))
        trace_emit(cid, "dead_letter", dl_start, now_ms(), "error", f"gave up after {attempt} attempts: {error}",
                   failed_stage=stage.name.lower(), attempts=attempt, topic=DEAD_LETTER_TOPIC)  # HW10: where the request ended
        log_fn(stage.label, f"gave up after {attempt} attempts: moved to {meta.topic} partition={meta.partition} "
                            f"offset={meta.offset} correlation_id={cid}")
        await consumer.commit()
        log_fn(stage.label, f"offset committed ({where}); the next message is not blocked")
        return

    for out in outs:
        kafka_key = None
        if stage.keyed and flags.task_key == "entity" and out.get("entity_key"):
            kafka_key = str(out["entity_key"]).encode("utf-8")
        meta = await producer.send_and_wait(stage.out_topic, dump(out).encode("utf-8"), key=kafka_key)
        log_fn(stage.label, f"sent topic={meta.topic} partition={meta.partition} offset={meta.offset} "
                            f"correlation_id={out.get('correlation_id')}"
                            + (f" key={kafka_key.decode()}" if kafka_key else "") + f" message={dump(out)}")
    if cid is not None:
        done.add(cid)
    if flags.commit_mode == "after":
        await consumer.commit()  # only now is the message fully handled
        log_fn(stage.label, f"offset committed ({where})")


async def run_stage(stage: Stage, consumer: Any, producer: Any, flags: Flags, done: Optional[DoneStore] = None,
                    log_fn: Callable[[str, str], None] = log) -> None:
    done = done if done is not None else DoneStore(
        os.path.join(flags.state_dir, f"{stage.label.lower()}_done.txt") if flags.state_dir else None)
    log_fn(stage.label, "Consumer is ready and listening...")
    log_fn(stage.label, f"reads {stage.in_topic} (group {stage.group}) -> writes {stage.out_topic}; "
                        f"mode={flags.mode} idempotent={flags.idempotent} commit={flags.commit_mode} "
                        f"max_attempts={flags.max_attempts or 'unlimited'} task_key={flags.task_key}")
    async for msg in consumer:
        await process_message(stage, msg, consumer, producer, done, flags, log_fn)


def _rebalance_listener(label: str) -> Any:
    from aiokafka.abc import ConsumerRebalanceListener

    class Listener(ConsumerRebalanceListener):
        def on_partitions_revoked(self, revoked: Any) -> None:
            if revoked:
                log(label, f"partitions revoked: {sorted((tp.topic, tp.partition) for tp in revoked)}")

        def on_partitions_assigned(self, assigned: Any) -> None:
            ps = sorted(tp.partition for tp in assigned)
            topic = next(iter(assigned)).topic if assigned else "-"
            log(label, f"partitions assigned: topic={topic} partitions={ps}")

    return Listener()


async def connect(stage: Stage) -> tuple:
    from aiokafka import AIOKafkaConsumer, AIOKafkaProducer  # late import: the offline tests need no Kafka client

    for attempt in range(1, 61):
        consumer = AIOKafkaConsumer(
            bootstrap_servers=BOOTSTRAP_SERVERS, group_id=stage.group, client_id=stage.label,
            auto_offset_reset="earliest", enable_auto_commit=False)
        consumer.subscribe([stage.in_topic], listener=_rebalance_listener(stage.label))
        producer = AIOKafkaProducer(bootstrap_servers=BOOTSTRAP_SERVERS, client_id=stage.label)
        try:
            await consumer.start()
            await producer.start()
            return consumer, producer
        except Exception as exc:  # noqa: BLE001
            log(stage.label, f"Kafka not ready at {BOOTSTRAP_SERVERS} (attempt {attempt}/60): {exc}")
            for closer in (consumer.stop, producer.stop):
                try:
                    await closer()
                except Exception:  # noqa: BLE001
                    pass
            await asyncio.sleep(3)
    raise SystemExit(f"{stage.label}: could not reach Kafka at {BOOTSTRAP_SERVERS}")


async def serve(stage: Stage, flags: Flags) -> None:
    print(f"{BANNER} | {stage.label} | mode={flags.mode}", flush=True)
    consumer, producer = await connect(stage)
    try:
        await run_stage(stage, consumer, producer, flags)
    finally:
        await consumer.stop()
        await producer.stop()


def main_for(make_stage: Callable[..., Stage], argv: Optional[List[str]] = None, instance_arg: bool = False) -> None:
    import argparse
    from kafka_agents.settings import load_flags

    parser = argparse.ArgumentParser()
    if instance_arg:
        parser.add_argument("--instance", default="A", help="name of this instance (several share one group)")
    args = parser.parse_args(argv)
    flags = load_flags()
    stage = make_stage(flags, getattr(args, "instance", None)) if instance_arg else make_stage(flags)
    try:
        asyncio.run(serve(stage, flags))
    except KeyboardInterrupt:
        print(f"[{stage.label}] stopped", flush=True)
