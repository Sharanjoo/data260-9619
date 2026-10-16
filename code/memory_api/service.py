"""HW6 Part 2 - one chat turn: save, load memory, compose, answer, remember."""
from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List

from pymongo.database import Database

from . import config
from .episodes import extract_facts, retrieve_episodes, store_facts, utc_now
from .prompt import build_messages, split_prompt_tokens
from .summaries import (
    latest_summary,
    maybe_update_lifetime_summary,
    should_summarize,
    update_session_summary,
)


def _iso(value) -> str:
    return value.isoformat().replace("+00:00", "Z") if value is not None else None


def save_message(db: Database, user_id: str, session_id: str, role: str, content: str) -> None:
    db[config.MESSAGES_COLLECTION].insert_one(
        {"user_id": user_id, "session_id": session_id, "role": role, "content": content, "created_at": utc_now()}
    )


def load_window(db: Database, user_id: str, session_id: str, n: int) -> List[Dict[str, Any]]:
    """Short-term memory: the last n messages of this session, oldest first."""
    docs = list(
        db[config.MESSAGES_COLLECTION]
        .find({"user_id": user_id, "session_id": session_id})
        .sort([("created_at", -1), ("_id", -1)])
        .limit(n)
    )
    docs.reverse()
    return [{"role": d["role"], "content": d["content"]} for d in docs]


def chat_turn(db: Database, chat_model, embedder, request) -> Dict[str, Any]:
    started = time.perf_counter()
    user_id = request.user_id
    session_id = request.session_id or f"sess-{uuid.uuid4().hex[:12]}"
    n = request.short_term_n or config.SHORT_TERM_N
    policy = request.compression_policy or config.COMPRESSION_POLICY

    read_only = bool(getattr(request, "read_only", False))

    # 1. save the user message, 2. load the short-term window (it ends with this message)
    if read_only:  # probe mode: the last n STORED messages plus the question; nothing is written
        window = load_window(db, user_id, session_id, n)
        window.append({"role": "user", "content": request.message})
    else:
        save_message(db, user_id, session_id, "user", request.message)
        window = load_window(db, user_id, session_id, n)

    # 3. long-term summaries
    lifetime_doc = latest_summary(db, user_id, "user")
    session_doc = latest_summary(db, user_id, "session", session_id)
    lifetime_text = lifetime_doc["text"] if lifetime_doc else None
    session_text = session_doc["text"] if session_doc else None

    # 4. episodic facts relevant to THIS message (retrieved before this message's own facts are stored)
    episodes = retrieve_episodes(db, embedder, user_id, request.message)

    # 5. compose the prompt and call the local model through the HW1 adapter
    messages, texts = build_messages(window, request.message, lifetime_text, session_text, episodes, policy)
    t0 = time.perf_counter()
    response = chat_model.complete(messages)
    reply_ms = (time.perf_counter() - t0) * 1000.0
    reply = response.content.strip()

    # 6. save the assistant reply
    if not read_only:
        save_message(db, user_id, session_id, "assistant", reply)

    # 7. remember: episodic facts from the user's message, then the summary triggers.
    #    Failures here must not lose a reply that is already saved.
    events: Dict[str, Any] = {
        "episodes_stored": [],
        "session_summary_updated": False,
        "lifetime_summary_updated": False,
        "warnings": [],
    }
    overhead_in = overhead_out = 0
    if not read_only:
        try:
            facts, tin, tout = extract_facts(chat_model, request.message)
            overhead_in += tin
            overhead_out += tout
            events["episodes_stored"] = store_facts(db, embedder, user_id, session_id, facts)
        except Exception as exc:  # noqa: BLE001
            events["warnings"].append(f"episode extraction failed: {exc}")

    user_count = db[config.MESSAGES_COLLECTION].count_documents(
        {"user_id": user_id, "session_id": session_id, "role": "user"}
    )
    if not read_only and should_summarize(user_count):
        try:
            text, tin, tout = update_session_summary(db, chat_model, user_id, session_id)
            overhead_in += tin
            overhead_out += tout
            events["session_summary_updated"] = text is not None
            life, tin, tout = maybe_update_lifetime_summary(db, chat_model, user_id)
            overhead_in += tin
            overhead_out += tout
            events["lifetime_summary_updated"] = life is not None
        except Exception as exc:  # noqa: BLE001
            events["warnings"].append(f"summarisation failed: {exc}")

    metrics = {
        "prompt_tokens": response.input_tokens,
        "completion_tokens": response.output_tokens,
        "tokens_by_component": split_prompt_tokens(texts, response.input_tokens),
        "reply_latency_ms": round(reply_ms, 1),
        "model_duration_ms": round(response.total_duration_ns / 1e6, 1),
        "latency_ms": round((time.perf_counter() - started) * 1000.0, 1),
        "memory_overhead_prompt_tokens": overhead_in,
        "memory_overhead_completion_tokens": overhead_out,
        "short_term_n": n,
        "compression_policy": policy,
        "read_only": read_only,
        "user_messages_in_session": user_count,
        "model": response.model,
    }
    memory_used = {
        "short_term": {"count": len(window), "limit": n, "messages": window},
        "long_term": {"lifetime_summary": lifetime_text, "session_summary": session_text},
        "episodic": episodes,
    }
    return {
        "user_id": user_id,
        "session_id": session_id,
        "reply": reply,
        "memory_used": memory_used,
        "memory_events": events,
        "metrics": metrics,
    }
