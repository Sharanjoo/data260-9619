"""Offline tests for src/notice_text.py, named test_<function>_<case> as AGENT.md requires."""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.notice_text import normalize_notice_title  # noqa: E402


def test_normalize_notice_title_collapses_whitespace() -> None:
    """Repeated spaces, tabs and newlines become single spaces."""
    assert normalize_notice_title("  Frozen \t Berries\nRecall  ") == "Frozen Berries Recall"


def test_normalize_notice_title_rejects_empty() -> None:
    """A title that is empty after trimming raises ValueError."""
    try:
        normalize_notice_title("   ")
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def test_normalize_notice_title_rejects_non_string() -> None:
    """A non-string title raises ValueError, not TypeError."""
    try:
        normalize_notice_title(123)  # type: ignore[arg-type]
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def test_normalize_notice_title_enforces_max_length() -> None:
    """Exactly the maximum length is accepted and one more character is rejected."""
    assert normalize_notice_title("x" * 100) == "x" * 100
    try:
        normalize_notice_title("x" * 101)
    except ValueError:
        return
    raise AssertionError("expected ValueError")
