"""HW6 Part 1: exercise the MongoDB document API end to end and print every result.

Needs the API running on PORT_BASE (docker compose up -d). Run from the repo root,
through the recorder so your name and timestamps land in reports/hw06/RUN_LOG.txt:

    python scripts/recorded_run_hw06.py -- python scripts/demo_doc_api_hw06.py

Exit code is 0 only if every request returned the status the API is supposed to return.
"""
from __future__ import annotations

import json
import os
import sys

import requests

BASE = os.environ.get("HW6_BASE_URL", "http://localhost:8619").rstrip("/")
URL = f"{BASE}/api/hw6/notices"
GOOD = {
    "title": "Demo Frozen Peas",
    "description": "Demo notice created by demo_doc_api_hw06.py",
    "status": "open",
    "category": "food-safety-recall",
    "notice_date": "2026-10-05T09:30:00Z",
}
failures = 0


def show(label: str, resp: requests.Response, expected: int) -> dict:
    global failures
    ok = resp.status_code == expected
    failures += 0 if ok else 1
    try:
        body = resp.json()
    except ValueError:
        body = resp.text
    text = json.dumps(body, ensure_ascii=False)
    print(f"[{'PASS' if ok else 'FAIL'}] {label}: HTTP {resp.status_code} (expected {expected})")
    print(f"       {text[:230]}{'...' if len(text) > 230 else ''}")
    return body if isinstance(body, dict) else {}


def main() -> int:
    print(f"HW6 Part 1 demo against {URL}\n\n--- CRUD ---")
    created = show("POST create", requests.post(URL, json=GOOD, timeout=10), 201)
    nid = created.get("id", "")
    lst = requests.get(URL, params={"limit": 3}, timeout=10)
    show("GET list (newest 3)", lst, 200)
    show("GET one", requests.get(f"{URL}/{nid}", timeout=10), 200)
    upd = dict(GOOD, title="Demo Frozen Peas (updated)", status="investigating")
    show("PUT update", requests.put(f"{URL}/{nid}", json=upd, timeout=10), 200)
    show("DELETE", requests.delete(f"{URL}/{nid}", timeout=10), 200)
    show("GET after delete", requests.get(f"{URL}/{nid}", timeout=10), 404)

    print("\n--- Validation (all must be rejected with 422) ---")
    cases = {
        "missing required title": {k: v for k, v in GOOD.items() if k != "title"},
        "missing required notice_date": {k: v for k, v in GOOD.items() if k != "notice_date"},
        "title longer than 100 chars": dict(GOOD, title="x" * 101),
        "invalid status enum": dict(GOOD, status="closed"),
        "invalid category enum": dict(GOOD, category="spoilage"),
        "wrong data type (title is a number)": dict(GOOD, title=123),
        "invalid date format": dict(GOOD, notice_date="yesterday"),
    }
    for label, body in cases.items():
        show(f"POST {label}", requests.post(URL, json=body, timeout=10), 422)
    show("POST malformed JSON", requests.post(URL, data="{bad json", headers={"Content-Type": "application/json"}, timeout=10), 422)
    show("GET malformed id", requests.get(f"{URL}/not-an-id", timeout=10), 422)
    show("GET unknown id", requests.get(f"{URL}/64b7f0f0f0f0f0f0f0f0f0f0", timeout=10), 404)

    print(f"\n{'ALL REQUESTS BEHAVED AS EXPECTED' if failures == 0 else f'{failures} UNEXPECTED RESULT(S)'}")
    return 1 if failures else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except requests.ConnectionError:
        print(f"Cannot reach {BASE}. Is the API running? (docker compose up -d)")
        sys.exit(2)
