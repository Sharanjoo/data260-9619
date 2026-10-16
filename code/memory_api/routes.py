"""HW6 Part 2 - route handlers: POST /api/chat, GET /api/memory/{user_id}, GET /api/aggregate/{user_id}."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Path as PathParam, Query
from fastapi.responses import FileResponse, JSONResponse
from pymongo.database import Database

from . import config
from .fingerprint import source_fingerprint
from .llm import ModelClientError, get_chat_model, get_embedder
from .schemas import ChatRequest, ChatResponse
from .service import _iso, chat_turn
from .store import get_database

router = APIRouter(tags=["hw6-memory"])
UserId = PathParam(pattern=config.ID_PATTERN, description="user id")


def _doc_out(doc: Dict[str, Any]) -> Dict[str, Any]:
    out = {k: v for k, v in doc.items() if k not in ("_id", "embedding")}
    out["id"] = str(doc["_id"])
    out["created_at"] = _iso(doc.get("created_at"))
    if "embedding" in doc:
        out["embedding_dim"] = len(doc["embedding"])
    return out


@router.post("/api/chat", response_model=ChatResponse)
def chat(
    body: ChatRequest,
    db: Database = Depends(get_database),
    chat_model=Depends(get_chat_model),
    embedder=Depends(get_embedder),
):
    """Save the message, assemble short/long-term/episodic memory, answer with the local model."""
    try:
        return chat_turn(db, chat_model, embedder, body)
    except ModelClientError as exc:
        return JSONResponse(status_code=502, content={"error": "model_unavailable", "message": str(exc)})


@router.get("/api/memory/{user_id}")
def get_memory(
    user_id: str = UserId,
    session_id: Optional[str] = Query(default=None, pattern=config.ID_PATTERN, description="limit messages to one session"),
    db: Database = Depends(get_database),
):
    """What the system currently remembers about a user."""
    from .summaries import latest_summary

    msg_query: Dict[str, Any] = {"user_id": user_id}
    if session_id:
        msg_query["session_id"] = session_id
    messages = list(
        db[config.MESSAGES_COLLECTION].find(msg_query).sort([("created_at", -1), ("_id", -1)]).limit(config.MEMORY_VIEW_MESSAGES)
    )
    messages.reverse()
    session_summary = latest_summary(db, user_id, "session", session_id)
    lifetime = latest_summary(db, user_id, "user")
    episodes = list(
        db[config.EPISODES_COLLECTION].find({"user_id": user_id}).sort([("created_at", -1), ("_id", -1)]).limit(config.MEMORY_VIEW_EPISODES)
    )
    return {
        "user_id": user_id,
        "messages": [_doc_out(m) for m in messages],
        "session_summary": _doc_out(session_summary) if session_summary else None,
        "lifetime_summary": _doc_out(lifetime) if lifetime else None,
        "episodes": [_doc_out(e) for e in episodes],
    }


@router.get("/api/aggregate/{user_id}")
def get_aggregate(user_id: str = UserId, db: Database = Depends(get_database)):
    """Daily message counts (grouped by date, aggregation pipeline) and the most recent summaries."""
    pipeline = [
        {"$match": {"user_id": user_id}},
        {
            "$group": {
                "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}},
                "messages": {"$sum": 1},
                "user_messages": {"$sum": {"$cond": [{"$eq": ["$role", "user"]}, 1, 0]}},
                "assistant_messages": {"$sum": {"$cond": [{"$eq": ["$role", "assistant"]}, 1, 0]}},
            }
        },
        {"$sort": {"_id": 1}},
    ]
    daily = [
        {
            "date": row["_id"],
            "messages": row["messages"],
            "user_messages": row["user_messages"],
            "assistant_messages": row["assistant_messages"],
        }
        for row in db[config.MESSAGES_COLLECTION].aggregate(pipeline)
    ]
    summaries = list(
        db[config.SUMMARIES_COLLECTION]
        .find({"user_id": user_id})
        .sort([("created_at", -1), ("_id", -1)])
        .limit(config.AGGREGATE_RECENT_SUMMARIES)
    )
    return {
        "user_id": user_id,
        "total_messages": sum(d["messages"] for d in daily),
        "sessions": len(db[config.MESSAGES_COLLECTION].distinct("session_id", {"user_id": user_id})),
        "episodes": db[config.EPISODES_COLLECTION].count_documents({"user_id": user_id}),
        "daily_message_counts": daily,
        "recent_summaries": [_doc_out(s) for s in summaries],
    }


@router.get("/memory-chat", include_in_schema=False)
def chat_page():
    """Optional mini chat page (one input box calling POST /api/chat)."""
    return FileResponse(Path(__file__).with_name("chat.html"))


@router.get("/api/memory-config")
def memory_config():
    """The settings and code fingerprint this server is running with (used by the Part 3 sweep)."""
    return {
        "short_term_n_default": config.SHORT_TERM_N,
        "summarize_every_user_msgs": config.SUMMARIZE_EVERY_USER_MSGS,
        "lifetime_every_session_summaries": config.LIFETIME_EVERY_SESSION_SUMMARIES,
        "episode_top_k": config.EPISODE_TOP_K,
        "episode_min_similarity": config.EPISODE_MIN_SIMILARITY,
        "compression_policy_default": config.COMPRESSION_POLICY,
        "chat_model": config.CHAT_MODEL,
        "embed_model": config.EMBED_MODEL,
        "source_fingerprint": source_fingerprint(),
    }
