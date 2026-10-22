"""Read-only probe of the recall data, used to pick the fixed Part 2 tasks. Run from the repo root:
   $env:MYSQL_PORT="43306"; python scripts/probe_recalls_hw07.py"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "mcp_servers"))

from domain_tools import recall_detail, search_recalls, source_recall_summary  # noqa: E402

print("Student: Sharan Lourduraj (SJSU 018169619)  PREFIX s9619")
first = search_recalls("a", 100)
print("search_recalls('a', 100) ok =", first["ok"], "rows =", len(first["data"] or []), first["error"] or "")
rows = first["data"] or []
for r in rows[:12]:
    print(f"  id={r['id']:<4} src={r['source_id']} units={r['units_affected']:<8} {r['product_name']!r} / {r['brand_name']!r}")
srcs = sorted({r["source_id"] for r in rows})
print("source ids seen:", srcs)
for s in srcs[:4]:
    print(" ", json.dumps(source_recall_summary(s)["data"]))
print("max id seen:", max((r["id"] for r in rows), default=None))
print("detail 999999 ->", json.dumps(recall_detail(999999)))
