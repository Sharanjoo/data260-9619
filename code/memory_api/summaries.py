"""HW6 Part 2 - long-term memory: session summaries every M user messages, and a
lifetime summary (scope 'user', session_id null) condensed from session summaries."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from pymongo.database import Database

from . import config
from .episodes import utc_now

SESSION_SUMMARY_PROMPT = (
    "You maintain a running summary of one chat conversation. Merge the previous summary (if any) "
    "with the new messages into at most 6 concise bullet points. Keep names, numbers, allergies, "
    "preferences, decisions and open questions. Output only the bullets, each starting with '- '."
)
LIFETIME_SUMMARY_PROMPT = (
    "You maintain a lifetime profile of one user from several conversation summaries. Merge the "
    "existing lifetime summary (if any) with the new session summaries into at most 8 concise "
    "bullet points about who the user is, lasting preferences, constraints and goals. If a newer "
    "summary contradicts an older one, keep the newer fact. Output only the bullets, each starting with '- '."
)


def latest_summary(db: Database, user_id: str, scope: str, session_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    query: Dict[str, Any] = {"user_id": user_id, "scope": scope}
    if scope == "session" and session_id is not None:
        query["session_id"] = session_id
    docs = list(db[config.SUMMARIES_COLLECTION].find(query).sort([("created_at", -1), ("_id", -1)]).limit(1))
    return docs[0] if docs else None


def _transcript(messages: List[Dict[str, Any]]) -> str:
    return "\n".join(f"{m['role']}: {m['content']}" for m in messages)


def _bullets(text: str) -> str:
    cleaned = text.strip()
    return cleaned


def should_summarize(user_message_count: int) -> bool:
    """Trigger: every SUMMARIZE_EVERY_USER_MSGS user messages in the session."""
    return user_message_count > 0 and user_message_count % config.SUMMARIZE_EVERY_USER_MSGS == 0


def update_session_summary(db: Database, chat_model, user_id: str, session_id: str) -> Tuple[Optional[str], int, int]:
    """Summarise the messages since the last session summary, merged with that summary."""
    previous = latest_summary(db, user_id, "session", session_id)
    query: Dict[str, Any] = {"user_id": user_id, "session_id": session_id}
    if previous:
        query["created_at"] = {"$gt": previous["created_at"]}
    new_messages = list(db[config.MESSAGES_COLLECTION].find(query).sort([("created_at", 1), ("_id", 1)]))
    if not new_messages and previous:
        return None, 0, 0
    user_content = (
        f"Previous summary:\n{previous['text'] if previous else '(none)'}\n\nNew messages:\n{_transcript(new_messages)}"
    )
    response = chat_model.complete(
        [{"role": "system", "content": SESSION_SUMMARY_PROMPT}, {"role": "user", "content": user_content}]
    )
    text = _bullets(response.content)
    if not text:
        return None, response.input_tokens, response.output_tokens
    db[config.SUMMARIES_COLLECTION].insert_one(
        {"user_id": user_id, "session_id": session_id, "scope": "session", "text": text, "created_at": utc_now()}
    )
    return text, response.input_tokens, response.output_tokens


def maybe_update_lifetime_summary(db: Database, chat_model, user_id: str) -> Tuple[Optional[str], int, int]:
    """'Occasionally': once LIFETIME_EVERY_SESSION_SUMMARIES new session summaries exist since the
    last lifetime summary, condense them (plus the old lifetime summary) into a new one."""
    lifetime = latest_summary(db, user_id, "user")
    query: Dict[str, Any] = {"user_id": user_id, "scope": "session"}
    if lifetime:
        query["created_at"] = {"$gt": lifetime["created_at"]}
    fresh = list(db[config.SUMMARIES_COLLECTION].find(query).sort([("created_at", 1), ("_id", 1)]))
    if len(fresh) < config.LIFETIME_EVERY_SESSION_SUMMARIES:
        return None, 0, 0
    # Only the newest summary of each session is needed: it already contains the earlier ones.
    newest_by_session: Dict[str, Dict[str, Any]] = {}
    for doc in fresh:
        newest_by_session[doc["session_id"]] = doc
    body = "\n\n".join(f"Session {sid}:\n{doc['text']}" for sid, doc in newest_by_session.items())
    user_content = f"Existing lifetime summary:\n{lifetime['text'] if lifetime else '(none)'}\n\nNew session summaries:\n{body}"
    response = chat_model.complete(
        [{"role": "system", "content": LIFETIME_SUMMARY_PROMPT}, {"role": "user", "content": user_content}]
    )
    text = _bullets(response.content)
    if not text:
        return None, response.input_tokens, response.output_tokens
    db[config.SUMMARIES_COLLECTION].insert_one(
        {"user_id": user_id, "session_id": None, "scope": "user", "text": text, "created_at": utc_now()}
    )
    return text, response.input_tokens, response.output_tokens
