"""Text helpers for recall notice titles, written to follow AGENT.md."""
from __future__ import annotations

import re

MAX_TITLE_LENGTH = 100
WHITESPACE_RUN = re.compile(r"\s+")


def normalize_notice_title(title: str, max_length: int = MAX_TITLE_LENGTH) -> str:
    """Trim a notice title, collapse repeated whitespace and enforce the maximum length."""
    if not isinstance(title, str):
        raise ValueError(f"title must be a string, got {type(title).__name__}")
    cleaned = WHITESPACE_RUN.sub(" ", title).strip()
    if not cleaned:
        raise ValueError("title must not be empty")
    if len(cleaned) > max_length:
        raise ValueError(f"title has {len(cleaned)} characters; the maximum is {max_length}")
    return cleaned
