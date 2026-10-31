"""HW8 Part 3 - the 20 related messages for the ordering test, generated from VERIFY_SEED, and the order check."""
from __future__ import annotations

import random
import uuid
from typing import Any, Dict, Iterable, List

from kafka_api.config import VERIFY_SEED
from kafka_agents.brain import STEPS_FAST

ENTITIES = ["frozen-berries", "peanut-butter", "spinach-bag", "chicken-nuggets", "infant-formula"]
UPDATES = ["recall announced", "affected lots listed", "retailers notified", "refund process opened",
           "FDA classification updated", "recall expanded", "recall closed"]


def ordering_messages(count: int = 20, seed: int = VERIFY_SEED, tag: str = "") -> List[Dict[str, Any]]:
    """`count` related messages for a few recall notices: the same seed always gives the same list, and several
    messages belong to the same notice (entity_key). `seq` is the order they are sent in. `tag` only changes the
    correlation ids, so the same 20 messages can be sent again in another run without looking like replays."""
    rng = random.Random(seed)
    per_entity = {e: 0 for e in ENTITIES}
    out: List[Dict[str, Any]] = []
    for seq in range(count):
        entity = rng.choice(ENTITIES)
        per_entity[entity] += 1
        step = per_entity[entity]
        out.append({
            "correlation_id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"s9619-{seed}-{tag}-{seq}" if tag else f"s9619-{seed}-{seq}")),
            "stage": "plan",
            "question": f"Update {step} for the {entity} recall notice: {UPDATES[(step - 1) % len(UPDATES)]}",
            "plan": {"steps": list(STEPS_FAST)},
            "entity_key": entity,
            "seq": seq,
        })
    return out


def order_violations(drafts: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """`drafts` in the order they finished. A violation is a message of the same entity that finished before
    an earlier-sent one (a smaller seq)."""
    seen: Dict[str, List[int]] = {}
    for d in drafts:
        seen.setdefault(d["entity_key"], []).append(d["seq"])
    detail = {}
    total = 0
    for entity, seqs in seen.items():
        bad = sum(1 for i in range(len(seqs)) for j in range(i + 1, len(seqs)) if seqs[i] > seqs[j])
        detail[entity] = {"finished_order": seqs, "out_of_order_pairs": bad}
        total += bad
    return {"total_out_of_order_pairs": total, "entities": detail}
