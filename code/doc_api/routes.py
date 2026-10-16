"""HW6 Part 1 - route handlers: CRUD over the recall_notices collection.

POST   /api/hw6/notices          create            -> 201
GET    /api/hw6/notices          list (filters)    -> 200
GET    /api/hw6/notices/{id}     one document      -> 200 / 404
PUT    /api/hw6/notices/{id}     replace fields    -> 200 / 404
DELETE /api/hw6/notices/{id}     delete            -> 200 / 404

A malformed id or invalid body is a 422 with a clear message, an unknown id is a
404, and a database failure becomes 500/503 (see errors.py).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, Query
from pymongo import DESCENDING, ReturnDocument
from pymongo.collection import Collection

from .config import API_PREFIX, DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from .mongo import get_notices_collection
from .schemas import (
    DeleteOut,
    NoticeCategory,
    NoticeCreate,
    NoticeOut,
    NoticeStatus,
    NoticeUpdate,
)

router = APIRouter(prefix=API_PREFIX, tags=["hw6-recall-notices"])


def get_collection() -> Collection:
    """FastAPI dependency; tests override this with an in-memory collection."""
    return get_notices_collection()


def _utc_now() -> datetime:
    """Current UTC time truncated to milliseconds -- MongoDB stores dates with
    millisecond precision, so this keeps the create response identical to what a
    later GET returns."""
    now = datetime.now(timezone.utc)
    return now.replace(microsecond=(now.microsecond // 1000) * 1000)


def _to_utc(value: datetime) -> datetime:
    """Naive datetimes are treated as UTC; aware ones are converted to UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _parse_id(notice_id: str) -> ObjectId:
    try:
        return ObjectId(notice_id)
    except (InvalidId, TypeError):
        raise HTTPException(
            status_code=422,
            detail=f"'{notice_id}' is not a valid id: expected a 24-character hex ObjectId",
        )


def _to_out(doc: Dict[str, Any]) -> NoticeOut:
    return NoticeOut(
        id=str(doc["_id"]),
        title=doc["title"],
        description=doc.get("description"),
        status=doc["status"],
        category=doc["category"],
        notice_date=doc["notice_date"],
        created_at=doc["created_at"],
        updated_at=doc["updated_at"],
    )


def _not_found(notice_id: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"Notice {notice_id} not found")


@router.post("", response_model=NoticeOut, status_code=201)
def create_notice(payload: NoticeCreate, col: Collection = Depends(get_collection)):
    now = _utc_now()
    doc = {
        "title": payload.title,
        "description": payload.description,
        "status": payload.status.value,
        "category": payload.category.value,
        "notice_date": _to_utc(payload.notice_date),
        "created_at": now,
        "updated_at": now,
    }
    doc["_id"] = col.insert_one(doc).inserted_id
    return _to_out(doc)


@router.get("", response_model=List[NoticeOut])
def list_notices(
    status: Optional[NoticeStatus] = Query(default=None, description="filter by status"),
    category: Optional[NoticeCategory] = Query(default=None, description="filter by category"),
    limit: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    skip: int = Query(default=0, ge=0),
    col: Collection = Depends(get_collection),
):
    """Newest first, so a document you just created is on the first page."""
    query: Dict[str, Any] = {}
    if status is not None:
        query["status"] = status.value
    if category is not None:
        query["category"] = category.value
    cursor = col.find(query).sort([("created_at", DESCENDING), ("_id", DESCENDING)]).skip(skip).limit(limit)
    return [_to_out(doc) for doc in cursor]


@router.get("/{notice_id}", response_model=NoticeOut)
def get_notice(notice_id: str, col: Collection = Depends(get_collection)):
    doc = col.find_one({"_id": _parse_id(notice_id)})
    if doc is None:
        raise _not_found(notice_id)
    return _to_out(doc)


@router.put("/{notice_id}", response_model=NoticeOut)
def update_notice(notice_id: str, payload: NoticeUpdate, col: Collection = Depends(get_collection)):
    updated = col.find_one_and_update(
        {"_id": _parse_id(notice_id)},
        {
            "$set": {
                "title": payload.title,
                "description": payload.description,
                "status": payload.status.value,
                "category": payload.category.value,
                "notice_date": _to_utc(payload.notice_date),
                "updated_at": _utc_now(),
            }
        },
        return_document=ReturnDocument.AFTER,
    )
    if updated is None:
        raise _not_found(notice_id)
    return _to_out(updated)


@router.delete("/{notice_id}", response_model=DeleteOut)
def delete_notice(notice_id: str, col: Collection = Depends(get_collection)):
    result = col.delete_one({"_id": _parse_id(notice_id)})
    if result.deleted_count == 0:
        raise _not_found(notice_id)
    return DeleteOut(deleted=True, id=notice_id)
