"""HW8 Part 2 - the three agent behaviours. Each handler gets one message and returns the message(s) for the
next topic; the correlation_id is copied through unchanged, so one question can be followed end to end."""
from __future__ import annotations

import asyncio
import random
from typing import Any, Dict, List, Optional

from kafka_api.config import VERIFY_SEED
from kafka_agents.brain import Brain, draft_checks
from kafka_agents.runtime import Stage
from kafka_agents.settings import (DRAFTS_TOPIC, FINAL_TOPIC, INBOX_TOPIC, PLANNER_GROUP, REVIEWER_GROUP,
                                   TASKS_TOPIC, WRITER_GROUP, Flags)

CARRY = ("seq", "entity_key", "expected_status")  # optional fields that ride along unchanged (used by the tests)


def _carry(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {k: payload[k] for k in CARRY if k in payload}


def _need_text(payload: Dict[str, Any], name: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is missing or empty")
    return value.strip()


def make_planner(flags: Flags, brain: Optional[Brain] = None) -> Stage:
    brain = brain or Brain(flags.mode)

    async def handle(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        cid = _need_text(payload, "correlation_id")
        question = _need_text(payload, "question")
        steps = await brain.plan(question)
        out = {"correlation_id": cid, "stage": "plan", "question": question, "plan": {"steps": steps},
               "entity_key": payload.get("entity_key") or f"question-{cid[:8]}"}
        out.update(_carry(payload))
        return [out]

    return Stage("PLANNER", "PLANNER", INBOX_TOPIC, PLANNER_GROUP, TASKS_TOPIC, handle, keyed=True)


def make_writer(flags: Flags, instance: str = "A", brain: Optional[Brain] = None) -> Stage:
    brain = brain or Brain(flags.mode)
    label = f"WRITER-{instance}"

    async def handle(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        cid = _need_text(payload, "correlation_id")
        question = _need_text(payload, "question")
        plan = payload.get("plan")
        steps = plan.get("steps") if isinstance(plan, dict) else None
        if not isinstance(steps, list) or not steps or not all(isinstance(s, str) and s.strip() for s in steps):
            raise ValueError("plan.steps must be a non-empty list of strings")
        pause = flags.write_delay_s
        if flags.jitter_s:  # seeded per message, so the same input always gets the same delay
            pause += random.Random(VERIFY_SEED + int(payload.get("seq", 0))).uniform(0, flags.jitter_s)
        if pause:
            await asyncio.sleep(pause)
        draft = await brain.write(question, steps)
        out = {"correlation_id": cid, "stage": "draft", "question": question, "plan": plan, "draft": draft,
               "writer": label}
        out.update(_carry(payload))
        return [out]

    return Stage("WRITER", label, TASKS_TOPIC, WRITER_GROUP, DRAFTS_TOPIC, handle)


def make_reviewer(flags: Flags, brain: Optional[Brain] = None) -> Stage:
    brain = brain or Brain(flags.mode)

    async def handle(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        cid = _need_text(payload, "correlation_id")
        question = _need_text(payload, "question")
        draft = _need_text(payload, "draft")
        checks = draft_checks(draft)
        approved, notes = await brain.review(question, draft)
        ok = approved and all(checks.values())
        out = {"correlation_id": cid, "stage": "final", "status": "approved" if ok else "rejected",
               "answer": draft, "question": question,
               "review": {"llm_approved": approved, "checks": checks, "notes": notes}}
        out.update(_carry(payload))
        return [out]

    return Stage("REVIEWER", "REVIEWER", DRAFTS_TOPIC, REVIEWER_GROUP, FINAL_TOPIC, handle)
