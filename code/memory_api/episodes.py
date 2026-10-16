"""HW6 Part 2 - episodic memory: extract up to 3 short facts per user message,
embed and store them, and retrieve the top-k by cosine similarity."""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Sequence

from pymongo.database import Database

from . import config

EXTRACTION_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "facts": {
            "type": "array",
            "maxItems": config.MAX_FACTS_PER_MESSAGE,
            "items": {
                "type": "object",
                "properties": {"fact": {"type": "string"}, "importance": {"type": "number"}},
                "required": ["fact", "importance"],
            },
        }
    },
    "required": ["facts"],
}

EXTRACTION_PROMPT = (
    "You extract durable facts about the USER from one chat message. "
    "Return JSON {\"facts\": [{\"fact\": str, \"importance\": number}]} with at most 3 facts. "
    "Only extract something the user STATES as true about themselves or the people close to them: identity, "
    "location, preferences, allergies and diets, constraints, family, plans or goals. "
    "Write each fact as a short third-person statement under 20 words. "
    "NEVER extract from questions, requests, hypotheticals or things the assistant might know: "
    "\"What should I do if I ate a recalled product?\" and \"Remind me what allergy I have\" contain NO facts. "
    "importance is between 0 and 1: 1 = must never be forgotten (allergies, health, safety), "
    "0.5 = useful preference or detail, 0.2 = small talk. "
    "Examples: \"I live in Austin and hate spicy food\" -> "
    "{\"facts\": [{\"fact\": \"User lives in Austin\", \"importance\": 0.5}, "
    "{\"fact\": \"User dislikes spicy food\", \"importance\": 0.4}]}; "
    "\"What is a recall?\" -> {\"facts\": []}. "
    "If there is no durable fact return {\"facts\": []}."
)


def utc_now() -> datetime:
    """UTC now truncated to milliseconds (MongoDB stores dates at ms precision)."""
    now = datetime.now(timezone.utc)
    return now.replace(microsecond=(now.microsecond // 1000) * 1000)


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def clean_facts(raw: Any) -> List[Dict[str, Any]]:
    """Validate what the model returned: <=3 facts, non-empty, trimmed, importance clipped to 0..1."""
    facts = raw.get("facts") if isinstance(raw, dict) else None
    out: List[Dict[str, Any]] = []
    seen = set()
    for item in facts if isinstance(facts, list) else []:
        if not isinstance(item, dict):
            continue
        text = str(item.get("fact", "")).strip().strip('"')[: config.MAX_FACT_CHARS]
        if not text or text.lower() in seen:
            continue
        try:
            importance = float(item.get("importance", 0.5))
        except (TypeError, ValueError):
            importance = 0.5
        seen.add(text.lower())
        out.append({"fact": text, "importance": round(min(1.0, max(0.0, importance)), 2)})
        if len(out) == config.MAX_FACTS_PER_MESSAGE:
            break
    return out


def extract_facts(chat_model, message: str) -> tuple[List[Dict[str, Any]], int, int]:
    """Ask the local model for facts. Returns (facts, prompt_tokens, completion_tokens)."""
    response = chat_model.complete(
        [{"role": "system", "content": EXTRACTION_PROMPT}, {"role": "user", "content": message}],
        json_schema=EXTRACTION_SCHEMA,
    )
    try:
        parsed = json.loads(response.content)
    except json.JSONDecodeError:
        parsed = {}
    return clean_facts(parsed), response.input_tokens, response.output_tokens


def store_facts(
    db: Database, embedder, user_id: str, session_id: str, facts: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Embed and insert each fact unless a near-identical one is already stored for this user."""
    col = db[config.EPISODES_COLLECTION]
    existing = list(
        col.find({"user_id": user_id}, {"embedding": 1}).sort("created_at", -1).limit(config.EPISODE_SCAN_LIMIT)
    )
    stored: List[Dict[str, Any]] = []
    for item in facts:
        vector = embedder.embed(item["fact"])
        if any(cosine(vector, e["embedding"]) >= config.EPISODE_DUPLICATE_SIMILARITY for e in existing):
            continue
        doc = {
            "user_id": user_id,
            "session_id": session_id,
            "fact": item["fact"],
            "importance": float(item["importance"]),
            "embedding": vector,
            "created_at": utc_now(),
        }
        col.insert_one(doc)
        existing.append({"embedding": vector})
        stored.append({"fact": item["fact"], "importance": item["importance"]})
    return stored


def retrieve_episodes(
    db: Database, embedder, user_id: str, query: str, top_k: int | None = None
) -> List[Dict[str, Any]]:
    """Top-k stored facts for this user ranked by cosine(query embedding, fact embedding)."""
    top_k = config.EPISODE_TOP_K if top_k is None else top_k
    docs = list(
        db[config.EPISODES_COLLECTION]
        .find({"user_id": user_id})
        .sort("created_at", -1)
        .limit(config.EPISODE_SCAN_LIMIT)
    )
    if not docs or top_k <= 0:
        return []
    query_vector = embedder.embed(query)
    scored = [(cosine(query_vector, d["embedding"]), d) for d in docs]
    scored = [pair for pair in scored if pair[0] >= config.EPISODE_MIN_SIMILARITY]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [
        {
            "fact": d["fact"],
            "importance": d["importance"],
            "similarity": round(score, 4),
            "session_id": d["session_id"],
            "created_at": d["created_at"].isoformat().replace("+00:00", "Z"),
        }
        for score, d in scored[:top_k]
    ]
