"""HW10 Part 2.1: gather the plan, the Writer draft and the Reviewer final answer of a request, joined by correlation_id.

Reads three Kafka topics from the beginning with its own throw-away consumer group (so it never disturbs the agents):
    s9619_tasks  -> the Planner's plan          s9619_drafts -> the Writer's draft          s9619_final -> the Reviewer's answer
The full original messages are kept in the bundle (plus topic / partition / offset / Kafka timestamp), so the evaluation can be
reproduced later from the saved bundle file without Kafka (load_bundles).

Bounded: one overall deadline for the scan; a message that is not valid JSON, not an object, or has no correlation_id is counted
and skipped; a request with a missing part comes back as an incomplete bundle instead of waiting forever."""
from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable, List

PARTS = {"plan": "TASKS_TOPIC", "draft": "DRAFTS_TOPIC", "final": "FINAL_TOPIC"}


def topics() -> Dict[str, str]:
    from kafka_agents import settings
    return {part: getattr(settings, name) for part, name in PARTS.items()}


def plan_text(plan: Any) -> str:
    steps = plan.get("steps") if isinstance(plan, dict) else None
    if not isinstance(steps, list):
        return ""
    return "\n".join(f"{i}. {s}" for i, s in enumerate(steps, 1) if isinstance(s, str))


def make_bundle(trace_id: str, found: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """found: part -> {"message": dict, "kafka": {...}}. Missing parts are listed, never invented."""
    msgs = {p: found[p]["message"] for p in PARTS if p in found}
    draft_msg, final_msg, plan_msg = msgs.get("draft", {}), msgs.get("final", {}), msgs.get("plan", {})
    question = next((m.get("question") for m in (draft_msg, plan_msg, final_msg) if isinstance(m.get("question"), str)), None)
    return {
        "trace_id": trace_id,
        "question": question,
        "plan": plan_msg.get("plan"),
        "draft": draft_msg.get("draft"),
        "final_answer": final_msg.get("answer"),
        "final_status": final_msg.get("status"),
        "review": final_msg.get("review"),
        "messages": msgs,
        "kafka": {p: found[p]["kafka"] for p in PARTS if p in found},
        "missing": [p for p in PARTS if p not in found],
    }


async def _scan(consumer: Any, part: str, wanted: set, found: Dict[str, Dict[str, Any]], stats: Dict[str, int]) -> None:
    async for msg in consumer:
        try:
            data = json.loads(msg.value.decode("utf-8"))
            if not isinstance(data, dict) or not isinstance(data.get("correlation_id"), str):
                raise ValueError("not an object with a correlation_id")
        except (ValueError, UnicodeDecodeError, AttributeError):
            stats["malformed"] += 1
            continue
        cid = data["correlation_id"]
        if cid not in wanted:
            continue
        slot = found.setdefault(cid, {})
        if part in slot:
            stats["duplicates"] += 1
            continue
        slot[part] = {"message": data, "kafka": {"topic": msg.topic, "partition": msg.partition, "offset": msg.offset,
                                                 "timestamp": getattr(msg, "timestamp", None)}}
        if all(all(p in found.get(c, {}) for p in [part]) for c in wanted):
            return  # every wanted request already has this part


async def collect_many(trace_ids: Iterable[str], consumers: Dict[str, Any], timeout_s: float = 45.0) -> Dict[str, Any]:
    """consumers: part -> async-iterable of Kafka records. Returns {"bundles": {cid: bundle}, "stats": {...}}."""
    wanted = set(trace_ids)
    found: Dict[str, Dict[str, Dict[str, Any]]] = {}
    stats = {"malformed": 0, "duplicates": 0, "timed_out": 0}

    async def one(part: str, consumer: Any) -> None:
        try:
            await asyncio.wait_for(_scan(consumer, part, wanted, found, stats), timeout_s)
        except asyncio.TimeoutError:
            stats["timed_out"] += 1

    await asyncio.gather(*(one(p, c) for p, c in consumers.items()))
    return {"bundles": {cid: make_bundle(cid, found.get(cid, {})) for cid in wanted}, "stats": stats}


async def collect_from_kafka(trace_ids: Iterable[str], timeout_s: float = 45.0) -> Dict[str, Any]:
    from aiokafka import AIOKafkaConsumer
    from kafka_api.config import BOOTSTRAP_SERVERS

    group = f"s9619-hw10-eval-{uuid.uuid4().hex[:8]}"
    consumers = {part: AIOKafkaConsumer(topic, bootstrap_servers=BOOTSTRAP_SERVERS, group_id=group,
                                        auto_offset_reset="earliest", enable_auto_commit=False)
                 for part, topic in topics().items()}
    started: List[Any] = []
    try:
        for c in consumers.values():
            await asyncio.wait_for(c.start(), timeout_s)
            started.append(c)
        return await collect_many(trace_ids, consumers, timeout_s)
    finally:
        for c in started:
            try:
                await c.stop()
            except Exception:  # noqa: BLE001
                pass


def save_bundles(bundles: Iterable[Dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for b in bundles:
            fh.write(json.dumps(b, ensure_ascii=False) + "\n")


def load_bundles(path: Path) -> Dict[str, Dict[str, Any]]:
    """Saved bundles (later lines win), keyed by trace_id."""
    out: Dict[str, Dict[str, Any]] = {}
    if not Path(path).exists():
        return out
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        try:
            b = json.loads(line)
        except ValueError:
            continue
        if isinstance(b, dict) and isinstance(b.get("trace_id"), str):
            out[b["trace_id"]] = b
    return out
