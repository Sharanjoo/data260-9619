"""HW6 Part 1 - PyMongo connection and collection setup.

This module is the only place that opens a MongoDB connection. Part 2's memory
collections (messages, summaries, episodes) reuse the same client/database.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.collection import Collection
from pymongo.database import Database

from .config import (
    DESCRIPTION_MAX_LENGTH,
    MONGO_DB_NAME,
    MONGO_URI,
    NOTICES_COLLECTION,
    SERVER_SELECTION_TIMEOUT_MS,
    TITLE_MAX_LENGTH,
)
from .schemas import NoticeCategory, NoticeStatus

_client: Optional[MongoClient] = None


def get_client() -> MongoClient:
    """One shared client per process. `tz_aware=True` so datetimes read back
    from MongoDB carry UTC tzinfo instead of being naive."""
    global _client
    if _client is None:
        _client = MongoClient(
            MONGO_URI,
            tz_aware=True,
            serverSelectionTimeoutMS=SERVER_SELECTION_TIMEOUT_MS,
        )
    return _client


def get_db() -> Database:
    return get_client()[MONGO_DB_NAME]


def get_notices_collection() -> Collection:
    return get_db()[NOTICES_COLLECTION]


def close_client() -> None:
    global _client
    if _client is not None:
        _client.close()
        _client = None


def notices_json_schema() -> Dict[str, Any]:
    """MongoDB-side validation rules: required fields, string length limits and
    enum constraints. Mirrors the Pydantic models in schemas.py."""
    return {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["title", "status", "category", "notice_date", "created_at", "updated_at"],
            "additionalProperties": False,
            "properties": {
                "_id": {"bsonType": "objectId"},
                "title": {
                    "bsonType": "string",
                    "minLength": 1,
                    "maxLength": TITLE_MAX_LENGTH,
                    "description": "required short text, 1-100 characters",
                },
                "description": {
                    "bsonType": ["string", "null"],
                    "maxLength": DESCRIPTION_MAX_LENGTH,
                    "description": "optional longer text",
                },
                "status": {
                    "enum": [s.value for s in NoticeStatus],
                    "description": "open | investigating | resolved",
                },
                "category": {
                    "enum": [c.value for c in NoticeCategory],
                    "description": "one of the four notice categories",
                },
                "notice_date": {"bsonType": "date", "description": "required date/time"},
                "created_at": {"bsonType": "date"},
                "updated_at": {"bsonType": "date"},
            },
        }
    }


def init_notices_collection(db: Optional[Database] = None) -> Collection:
    """Create the collection with its validator (or refresh the validator if the
    collection already exists) and make sure the indexes exist. Safe to re-run."""
    db = db if db is not None else get_db()
    validator = notices_json_schema()
    if NOTICES_COLLECTION in db.list_collection_names():
        db.command(
            "collMod",
            NOTICES_COLLECTION,
            validator=validator,
            validationLevel="strict",
            validationAction="error",
        )
    else:
        db.create_collection(
            NOTICES_COLLECTION,
            validator=validator,
            validationLevel="strict",
            validationAction="error",
        )
    col = db[NOTICES_COLLECTION]
    col.create_index([("created_at", DESCENDING)], name="created_at_desc")
    col.create_index([("status", ASCENDING)], name="status_1")
    col.create_index([("category", ASCENDING)], name="category_1")
    return col
