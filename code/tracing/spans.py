"""HW10 Part 4.1: structured spans, one JSON line per pipeline stage.

    {"trace_id": "<correlation_id>", "stage": "writer", "start": "...Z", "end": "...Z", "start_ms": 1.7e12,
     "end_ms": 1.7e12, "duration_ms": 41234.5, "status": "ok" | "error" | "timeout", "error": null | "text",
     "attrs": {...}, "pid": 1234}

trace_id IS the correlation_id that HW8 already puts on every message (inbox, tasks, drafts, final): there is no second
request id and nothing is joined afterwards. Every agent process appends its own spans to the same file
(reports/hw10/raw/spans.jsonl, or HW10_SPANS_PATH); each span is one short line written with one append, so
the Planner, Writer, Reviewer and the ingress can write at the same time.

Tracing must never break a request: any failure while writing a span is swallowed.
Offline test scripts (test_*.py) do not write spans unless HW10_SPANS_PATH is set explicitly; HW10_TRACE_OFF=1 turns it off.
"""
from __future__ import annotations

import json
import os
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, Optional

REPO = Path(__file__).resolve().parents[2]
DEFAULT_PATH = REPO / "reports" / "hw10" / "raw" / "spans.jsonl"


def spans_path() -> Optional[Path]:
    """Where spans go right now, or None when tracing is off."""
    if os.environ.get("HW10_TRACE_OFF", "").strip().lower() in ("1", "true", "yes", "on"):
        return None
    explicit = os.environ.get("HW10_SPANS_PATH")
    if explicit:
        return Path(explicit)
    if Path(sys.argv[0] or "").name.startswith("test_"):
        return None
    return DEFAULT_PATH


def now_ms() -> float:
    return time.time() * 1000.0


def _iso(ms: float) -> str:
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def emit(trace_id: Optional[str], stage: str, start_ms: float, end_ms: float, status: str = "ok",
         error: Optional[str] = None, **attrs: Any) -> Optional[Dict[str, Any]]:
    """Write one span. Returns the record (or None when tracing is off or there is no trace_id)."""
    path = spans_path()
    if path is None or not trace_id:
        return None
    record = {"trace_id": trace_id, "stage": stage, "start": _iso(start_ms), "end": _iso(end_ms),
              "start_ms": round(start_ms, 3), "end_ms": round(end_ms, 3),
              "duration_ms": round(max(end_ms - start_ms, 0.0), 3), "status": status,
              "error": (error[:500] if error else None), "attrs": attrs, "pid": os.getpid()}
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, ensure_ascii=False, default=str) + "\n"
        with path.open("a", encoding="utf-8", newline="") as fh:
            fh.write(line)
    except Exception:  # noqa: BLE001 - tracing must never break the request
        return None
    return record


@contextmanager
def span(trace_id: Optional[str], stage: str, **attrs: Any) -> Iterator[Dict[str, Any]]:
    """Time a block. Add more attributes inside the block through the yielded dict. An exception marks the span
    status=error with the error text and is re-raised."""
    extra: Dict[str, Any] = dict(attrs)
    start = now_ms()
    try:
        yield extra
    except Exception as exc:  # noqa: BLE001
        emit(trace_id, stage, start, now_ms(), "error", f"{type(exc).__name__}: {exc}", **extra)
        raise
    emit(trace_id, stage, start, now_ms(), extra.pop("_status", "ok"), extra.pop("_error", None), **extra)


def read_spans(path: Optional[Path] = None) -> list:
    """All spans in the file (bad lines skipped)."""
    p = Path(path) if path else DEFAULT_PATH
    out: list = []
    if not p.exists():
        return out
    with p.open(encoding="utf-8") as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if isinstance(rec, dict) and "trace_id" in rec and "stage" in rec:
                out.append(rec)
    return out
