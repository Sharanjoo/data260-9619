"""HW6 Part 2 - the three memory collections (messages, summaries, episodes).

They live in the same database as Part 1 (s9619_doc) and reuse doc_api's PyMongo
connection. Part 1's recall_notices collection is never touched here.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from pymongo import ASCENDING, DESCENDING
from pymongo.database import Database
from pymongo.errors import CollectionInvalid

from doc_api.mongo import get_db

from .config import EPISODES_COLLECTION, MESSAGES_COLLECTION, SUMMARIES_COLLECTION

_STR = {"bsonType": "string", "minLength": 1}


def messages_json_schema() -> Dict[str, Any]:
    return {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["user_id", "session_id", "role", "content", "created_at"],
            "properties": {
                "_id": {"bsonType": "objectId"},
                "user_id": _STR,
                "session_id": _STR,
                "role": {"enum": ["user", "assistant"]},
                "content": {"bsonType": "string"},
                "created_at": {"bsonType": "date"},
            },
            "additionalProperties": False,
        }
    }


def summaries_json_schema() -> Dict[str, Any]:
    return {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["user_id", "session_id", "scope", "text", "created_at"],
            "properties": {
                "_id": {"bsonType": "objectId"},
                "user_id": _STR,
                "session_id": {"bsonType": ["string", "null"]},   # null for the lifetime summary
                "scope": {"enum": ["session", "user"]},
                "text": {"bsonType": "string", "minLength": 1},
                "created_at": {"bsonType": "date"},
            },
            "additionalProperties": False,
        }
    }


def episodes_json_schema() -> Dict[str, Any]:
    return {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["user_id", "session_id", "fact", "importance", "embedding", "created_at"],
            "properties": {
                "_id": {"bsonType": "objectId"},
                "user_id": _STR,
                "session_id": _STR,
                "fact": {"bsonType": "string", "minLength": 1, "maxLength": 200},
                "importance": {"bsonType": "number", "minimum": 0, "maximum": 1},
                "embedding": {"bsonType": "array", "items": {"bsonType": "number"}},
                "created_at": {"bsonType": "date"},
            },
            "additionalProperties": False,
        }
    }


def _ensure_collection(db: Database, name: str, validator: Dict[str, Any]) -> None:
    try:
        db.create_collection(name, validator=validator, validationLevel="strict", validationAction="error")
    except CollectionInvalid:
        # Already exists: refresh the validator in place (keeps existing documents).
        db.command("collMod", name, validator=validator, validationLevel="strict", validationAction="error")


def init_memory_collections(db: Optional[Database] = None) -> Dict[str, Any]:
    """Create/refresh the three collections with validators and indexes. Safe to re-run."""
    db = db if db is not None else get_db()
    _ensure_collection(db, MESSAGES_COLLECTION, messages_json_schema())
    _ensure_collection(db, SUMMARIES_COLLECTION, summaries_json_schema())
    _ensure_collection(db, EPISODES_COLLECTION, episodes_json_schema())

    db[MESSAGES_COLLECTION].create_index(
        [("user_id", ASCENDING), ("session_id", ASCENDING), ("created_at", DESCENDING)], name="user_session_time"
    )
    db[MESSAGES_COLLECTION].create_index([("user_id", ASCENDING), ("created_at", DESCENDING)], name="user_time")
    db[SUMMARIES_COLLECTION].create_index(
        [("user_id", ASCENDING), ("scope", ASCENDING), ("created_at", DESCENDING)], name="user_scope_time"
    )
    db[EPISODES_COLLECTION].create_index([("user_id", ASCENDING), ("created_at", DESCENDING)], name="user_time")
    return {"database": db.name, "collections": [MESSAGES_COLLECTION, SUMMARIES_COLLECTION, EPISODES_COLLECTION]}


def get_database() -> Database:
    """FastAPI dependency (tests override it with a mongomock database)."""
    return get_db()
