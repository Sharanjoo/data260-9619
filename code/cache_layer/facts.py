"""HW9 Parts 2-3: the database record an answer depends on.

A question that names a recall record (REC-000000) is answered from that MySQL row, so the cache entry for it records
which record it depends on (depends_on) and a fingerprint of the facts it was built from (data_version). The
fingerprint is a hash of the fields the answer can mention, not updated_at: the view counter of Part 1 rewrites the
row every 10 accesses, and that must not make every cached answer look out of date."""
from __future__ import annotations

import hashlib
import re
from typing import Any, Callable, Optional

from sqlalchemy import text

RECORD_CODE = re.compile(r"\bREC-\d{6}\b", re.IGNORECASE)
SQL = text(
    "SELECT r.record_code, r.product_name, r.brand_name, r.units_affected, s.source_name, s.source_region "
    "FROM recall_record r LEFT JOIN recall_source s ON s.id = r.source_id WHERE r.record_code = :code")


def find_record_code(query: str) -> Optional[str]:
    m = RECORD_CODE.search(query)
    return m.group(0).upper() if m else None


def facts_text(f: dict) -> str:
    return (f"Facts from the recall database for {f['record_code']}: product {f['product_name']}; brand "
            f"{f['brand_name']}; units affected {f['units_affected']}; reported by {f['source_name']} "
            f"({f['source_region']}). Answer the question from these facts, then add one sentence telling shoppers "
            "not to eat or use the recalled product and to follow the official recall notice.")


def fingerprint(f: dict) -> str:
    raw = "|".join(str(f[k]) for k in ("record_code", "product_name", "brand_name", "units_affected",
                                       "source_name", "source_region"))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


class FactsStore:
    def __init__(self, session_factory: Optional[Callable[[], Any]] = None) -> None:
        if session_factory is None:
            from db import SessionLocal
            session_factory = SessionLocal
        self.session_factory = session_factory

    def load(self, code: str) -> Optional[dict]:
        with self.session_factory() as session:
            row = session.execute(SQL, {"code": code}).mappings().first()
        return dict(row) if row else None

    def version(self, code: str) -> Optional[str]:
        f = self.load(code)
        return fingerprint(f) if f else None
