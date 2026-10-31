"""HW8 Part 1 - the worker's business logic as plain functions (no Kafka in here, so it can be tested alone).

Entities live in a plain Python dictionary inside the worker (the exercise says so).
A repeated correlation_id (Kafka may deliver a message twice) returns the stored response and
creates nothing new: that is the idempotency used again in Part 3.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from .config import CATEGORIES, OPERATIONS

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
FIELDS = ("productName", "brandName", "submitterEmail", "description", "category", "termsAccepted")


def _text(data: Dict[str, Any], key: str, max_len: int) -> Tuple[Optional[str], Optional[str]]:
    if key not in data:
        return None, f"{key} is required"
    value = data[key]
    if not isinstance(value, str):
        return None, f"{key} must be text"
    value = value.strip()
    if not value:
        return None, f"{key} must not be empty"
    if len(value) > max_len:
        return None, f"{key} must be at most {max_len} characters"
    return value, None


def validate_recall_notice(data: Any) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Return (clean_fields, None) or (None, error message). Missing, empty and invalid values are rejected."""
    if not isinstance(data, dict):
        return None, "data must be an object"
    unknown = sorted(set(data) - set(FIELDS))
    if unknown:
        return None, f"unknown field: {unknown[0]}"
    clean: Dict[str, Any] = {}
    for key, limit in (("productName", 100), ("brandName", 100), ("submitterEmail", 254), ("description", 1000)):
        value, error = _text(data, key, limit)
        if error:
            return None, error
        clean[key] = value
    if not EMAIL_RE.match(clean["submitterEmail"]):
        return None, "submitterEmail must be a valid email address"
    if len(clean["description"]) <= 25:
        return None, "description must be longer than 25 characters"
    category = data.get("category")
    if "category" not in data:
        return None, "category is required"
    if category not in CATEGORIES:
        return None, "category must be one of: " + ", ".join(CATEGORIES)
    clean["category"] = category
    if "termsAccepted" not in data:
        return None, "termsAccepted is required"
    if data["termsAccepted"] is not True:
        return None, "termsAccepted must be true"
    clean["termsAccepted"] = True
    return clean, None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class RecallNoticeStore:
    """The worker's in-memory store plus the request handler."""

    def __init__(self, idempotent: bool = True) -> None:
        self.notices: Dict[str, Dict[str, Any]] = {}
        self.idempotent = idempotent
        self.answered: Dict[str, Dict[str, Any]] = {}  # correlation_id -> response already sent
        self.duplicates_ignored = 0

    def handle(self, request: Any) -> Dict[str, Any]:
        """Turn one request message into one response message. Never raises; the correlation_id is always echoed."""
        cid = request.get("correlation_id") if isinstance(request, dict) else None
        if not isinstance(request, dict):
            return {"correlation_id": cid, "success": False, "error": "Request must be a JSON object"}
        if not cid or not isinstance(cid, str):
            return {"correlation_id": cid, "success": False, "error": "correlation_id is required"}
        if self.idempotent and cid in self.answered:
            self.duplicates_ignored += 1
            return dict(self.answered[cid])
        response = self._dispatch(cid, request.get("operation"), request.get("data"))
        if self.idempotent:
            self.answered[cid] = dict(response)
        return response

    def _dispatch(self, cid: str, operation: Any, data: Any) -> Dict[str, Any]:
        if operation not in OPERATIONS:
            return {"correlation_id": cid, "success": False, "error": "Unknown operation"}
        if operation == "CREATE_RECALL_NOTICE":
            clean, error = validate_recall_notice(data)
            if error:
                return {"correlation_id": cid, "success": False, "error": error}
            notice_id = str(uuid.uuid4())
            self.notices[notice_id] = {"recall_notice_id": notice_id, **clean, "submissionDate": _now()}
            return {"correlation_id": cid, "success": True, "recall_notice_id": notice_id,
                    "message": "Recall notice created"}
        # GET_RECALL_NOTICE
        if not isinstance(data, dict) or not isinstance(data.get("recall_notice_id"), str) \
                or not data["recall_notice_id"].strip():
            return {"correlation_id": cid, "success": False, "error": "recall_notice_id is required"}
        notice = self.notices.get(data["recall_notice_id"])
        if notice is None:
            return {"correlation_id": cid, "success": False, "error": "Recall notice not found"}
        return {"correlation_id": cid, "success": True, "recall_notice": dict(notice)}
