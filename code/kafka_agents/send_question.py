"""Client: put one question on s9619_inbox and wait for the matching answer on s9619_final.

   python code/kafka_agents/send_question.py                       (new correlation_id, default question)
   python code/kafka_agents/send_question.py --question "..." --entity-key berries-lot-7
   python code/kafka_agents/send_question.py --correlation-id <same id>   (replays a question: duplicate delivery)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kafka_api.config import BOOTSTRAP_SERVERS  # noqa: E402
from kafka_api.logutil import log  # noqa: E402
from kafka_agents.runtime import dump  # noqa: E402
from kafka_agents.settings import BANNER, FINAL_TOPIC, INBOX_TOPIC  # noqa: E402

DEFAULT_QUESTION = ("I bought Frozen Mixed Berries from Northfield Farms that were recalled for possible "
                    "Hepatitis A contamination. What should I do with the bag I already have?")


async def wait_for_final(consumer: Any, cid: str, after_ts: int, timeout: float) -> Optional[Dict[str, Any]]:
    """First message on the final topic with this correlation_id that was written after the question was sent."""
    async def scan() -> Optional[Dict[str, Any]]:
        async for msg in consumer:
            if getattr(msg, "timestamp", 0) < after_ts:
                continue
            try:
                data = json.loads(msg.value.decode("utf-8"))
            except ValueError:
                continue
            if isinstance(data, dict) and data.get("correlation_id") == cid:
                log("CLIENT", f"final message received topic={msg.topic} partition={msg.partition} "
                              f"offset={msg.offset} correlation_id={cid}")
                return data
        return None
    try:
        return await asyncio.wait_for(scan(), timeout)
    except asyncio.TimeoutError:
        return None


async def ask(producer: Any, consumer: Any, question: str, cid: str, entity_key: Optional[str],
              timeout: float, seq: Optional[int] = None) -> Optional[Dict[str, Any]]:
    message: Dict[str, Any] = {"correlation_id": cid, "question": question}
    if entity_key:
        message["entity_key"] = entity_key
    if seq is not None:
        message["seq"] = seq
    meta = await producer.send_and_wait(INBOX_TOPIC, dump(message).encode("utf-8"))
    log("CLIENT", f"sent question topic={meta.topic} partition={meta.partition} offset={meta.offset} "
                  f"correlation_id={cid} message={dump(message)}")
    if timeout <= 0:
        return None
    return await wait_for_final(consumer, cid, getattr(meta, "timestamp", 0), timeout)


async def main() -> int:
    from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

    parser = argparse.ArgumentParser()
    parser.add_argument("--question", default=DEFAULT_QUESTION)
    parser.add_argument("--correlation-id", default=None, help="reuse an id to replay a question")
    parser.add_argument("--entity-key", default=None)
    parser.add_argument("--timeout", type=float, default=300.0, help="seconds to wait for the final message (0 = do not wait)")
    parser.add_argument("--output-json", default=None, help="also save the final message to this file")
    args = parser.parse_args()
    cid = args.correlation_id or str(uuid.uuid4())

    print(BANNER + " | send_question", flush=True)
    consumer = AIOKafkaConsumer(FINAL_TOPIC, bootstrap_servers=BOOTSTRAP_SERVERS,
                                group_id=f"s9619-client-{uuid.uuid4().hex[:8]}", auto_offset_reset="earliest",
                                enable_auto_commit=False)
    producer = AIOKafkaProducer(bootstrap_servers=BOOTSTRAP_SERVERS)
    await consumer.start()
    await producer.start()
    try:
        final = await ask(producer, consumer, args.question, cid, args.entity_key, args.timeout)
    finally:
        await consumer.stop()
        await producer.stop()
    if args.timeout <= 0:
        return 0
    if final is None:
        log("CLIENT", f"no final message for correlation_id={cid} within {args.timeout:.0f}s")
        return 1
    print(json.dumps({k: final[k] for k in ("correlation_id", "status", "answer") if k in final}, indent=2,
                     ensure_ascii=False))
    log("CLIENT", f"correlation_id preserved from question to final answer: "
                  f"{'YES' if final.get('correlation_id') == cid else 'NO'}")
    if args.output_json:
        Path(args.output_json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output_json).write_text(json.dumps(final, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0 if final.get("status") == "approved" else 2


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
