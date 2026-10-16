"""HW6 Part 1 - Pydantic data models for the recall-notice documents.

Pydantic is the first line of validation (clear 422 errors before anything
touches the database); mongo.py installs the same rules as a MongoDB
$jsonSchema validator as the second line.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated, Optional

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from .config import DESCRIPTION_MAX_LENGTH, TITLE_MAX_LENGTH


class NoticeStatus(str, Enum):
    """Lifecycle of a recall notice. Defaults to `open`."""

    open = "open"
    investigating = "investigating"
    resolved = "resolved"


class NoticeCategory(str, Enum):
    """The four notice categories from DOMAIN_SCHEMA.md (HW2)."""

    food_safety_recall = "food-safety-recall"
    allergen_alert = "allergen-alert"
    quality_withdrawal = "quality-withdrawal"
    supply_shortage = "supply-shortage"


# Required short text: whitespace-trimmed, 1..100 characters.
Title = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=TITLE_MAX_LENGTH),
]


class NoticeFields(BaseModel):
    """Fields a client may set. Unknown fields are rejected (extra=forbid), so a
    typo such as `statuss` is a clear 422 instead of being silently ignored."""

    model_config = ConfigDict(extra="forbid")

    title: Title
    description: Optional[str] = Field(default=None, max_length=DESCRIPTION_MAX_LENGTH)
    status: NoticeStatus = NoticeStatus.open
    category: NoticeCategory
    notice_date: datetime

    @field_validator("description")
    @classmethod
    def _blank_description_is_none(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        return value or None


class NoticeCreate(NoticeFields):
    """Body of POST /api/hw6/notices."""


class NoticeUpdate(NoticeFields):
    """Body of PUT /api/hw6/notices/{id}: replaces every client-settable field."""


class NoticeOut(BaseModel):
    """What the API returns. `id` is the MongoDB ObjectId as a string."""

    id: str
    title: str
    description: Optional[str] = None
    status: NoticeStatus
    category: NoticeCategory
    notice_date: datetime
    created_at: datetime
    updated_at: datetime


class DeleteOut(BaseModel):
    deleted: bool
    id: str
