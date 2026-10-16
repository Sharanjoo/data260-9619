"""HW6 Part 2 - request/response models for the three memory endpoints."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from .config import ID_PATTERN, MAX_MESSAGE_CHARS


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(pattern=ID_PATTERN, description="who is talking")
    session_id: Optional[str] = Field(default=None, pattern=ID_PATTERN, description="omit to start a new session")
    message: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)
    # Experiment overrides used by the Part 3 sweep (defaults come from the environment).
    short_term_n: Optional[int] = Field(default=None, ge=1, le=100)
    compression_policy: Optional[str] = Field(default=None, pattern=r"^(none|compress_old_assistant)$")
    # Probe mode: answer using memory but store nothing (no messages, facts or summaries are written).
    read_only: bool = False


class ChatResponse(BaseModel):
    user_id: str
    session_id: str
    reply: str
    memory_used: Dict[str, Any]
    memory_events: Dict[str, Any]
    metrics: Dict[str, Any]
