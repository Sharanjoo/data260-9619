"""HW5 Part 2B: domain logic for the <PREFIX>_rel (s9619_rel) database.

Three plain Python functions -- no MCP/FastMCP import here -- each
returning the single {ok, data, error} envelope required by Part 2B
(error is None on success):

    search_recalls(query, limit)       -- search
    recall_detail(record_id)           -- detail lookup
    source_recall_summary(source_id)   -- aggregate operation

Kept separate from domain_server.py (the MCP wrapper) on purpose: Part 4's
execute_tool() imports these same functions directly and reuses the exact
same envelope/validation/error strings, rather than redefining the logic or
round-tripping through MCP. "Define it once here and carry it through."

DB access reuses code/db.py's SessionLocal/engine (same models, same
MYSQL_* env vars read there). This process runs OUTSIDE Docker (on your
host, via `mcp dev domain_server.py` or directly from execute_tool), so set
MYSQL_PORT=43306 before running anything that imports this module --
compose.yaml maps MySQL to host port 43306, and code/db.py's MYSQL_PORT
default of 3306 only works for code running inside the `web` container on
the Docker-internal network.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "code"))

# This package only ever runs on the host (via `mcp dev` / the Inspector / a
# plain `python` invocation for Part 4) -- never inside the `web` container,
# unlike code/db.py itself (shared, and correctly defaults MYSQL_PORT to 3306
# for in-container use). setdefault (not a hard override) so an explicitly
# set MYSQL_PORT still wins -- but on Windows, launching this through
# `npx @modelcontextprotocol/inspector ...` spawns python via Node's
# child_process, which does NOT reliably forward a parent shell's env vars
# (confirmed: $env:MYSQL_PORT="43306" in PowerShell did not reach the
# spawned process), so relying on that alone silently connected to whatever
# else was listening on the host's default port 3306 instead -- hence this
# fallback to the compose.yaml host-side port mapping (43306:3306).
os.environ.setdefault("MYSQL_PORT", "43306")

from db import RecallRecord, RecallSource, SessionLocal  # noqa: E402


def _envelope(ok: bool, data: Any = None, error: Optional[str] = None) -> dict:
    return {"ok": ok, "data": data, "error": error}


def _record_to_dict(rec: RecallRecord) -> dict:
    return {
        "id": rec.id,
        "product_name": rec.product_name,
        "brand_name": rec.brand_name,
        "record_code": rec.record_code,
        "units_affected": rec.units_affected,
        "source_id": rec.source_id,
        "source_name": rec.source.source_name if rec.source else None,
        "source_region": rec.source.source_region if rec.source else None,
        "created_at": rec.created_at.isoformat() if rec.created_at else None,
        "updated_at": rec.updated_at.isoformat() if rec.updated_at else None,
    }


def search_recalls(query: str, limit: int = 10) -> dict:
    """Search: case-insensitive substring match on product_name or brand_name.

    Invalid-call example (documented in Part 3): query="" or limit=0 -> ok=False.
    """
    if not isinstance(query, str) or not query.strip():
        return _envelope(False, error="query must be a non-empty string")
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        return _envelope(False, error="limit must be an integer between 1 and 100")
    if not (1 <= limit <= 100):
        return _envelope(False, error="limit must be an integer between 1 and 100")

    db = SessionLocal()
    try:
        like = f"%{query.strip()}%"
        rows = (
            db.query(RecallRecord)
            .filter(
                (RecallRecord.product_name.ilike(like))
                | (RecallRecord.brand_name.ilike(like))
            )
            .order_by(RecallRecord.id.asc())
            .limit(limit)
            .all()
        )
        return _envelope(True, data=[_record_to_dict(r) for r in rows])
    except Exception as exc:  # noqa: BLE001 -- convert to clean envelope, never raise
        return _envelope(False, error=f"search_recalls failed: {exc}")
    finally:
        db.close()


def recall_detail(record_id: int) -> dict:
    """Detail lookup: a single recall record by id.

    Invalid-call example (documented in Part 3): a non-existent record_id -> ok=False.
    """
    try:
        record_id = int(record_id)
    except (TypeError, ValueError):
        return _envelope(False, error="record_id must be an integer")

    db = SessionLocal()
    try:
        rec = db.get(RecallRecord, record_id)
        if rec is None:
            return _envelope(False, error=f"no recall record with id {record_id}")
        return _envelope(True, data=_record_to_dict(rec))
    except Exception as exc:  # noqa: BLE001
        return _envelope(False, error=f"recall_detail failed: {exc}")
    finally:
        db.close()


def source_recall_summary(source_id: int) -> dict:
    """Aggregate: record count + total units_affected for one recall source.

    Invalid-call example (documented in Part 3): a non-existent source_id -> ok=False.
    """
    try:
        source_id = int(source_id)
    except (TypeError, ValueError):
        return _envelope(False, error="source_id must be an integer")

    db = SessionLocal()
    try:
        source = db.get(RecallSource, source_id)
        if source is None:
            return _envelope(False, error=f"no recall source with id {source_id}")
        rows = db.query(RecallRecord).filter(RecallRecord.source_id == source_id).all()
        total_units = sum(r.units_affected or 0 for r in rows)
        return _envelope(
            True,
            data={
                "source_id": source.id,
                "source_name": source.source_name,
                "source_region": source.source_region,
                "source_code": source.source_code,
                "record_count": len(rows),
                "total_units_affected": total_units,
            },
        )
    except Exception as exc:  # noqa: BLE001
        return _envelope(False, error=f"source_recall_summary failed: {exc}")
    finally:
        db.close()
