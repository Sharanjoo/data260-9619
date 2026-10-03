"""HW5 Part 5.I: demonstrate the safety rule -- one allowed call, one
blocked call.

Uses execute_tool's real, database-backed registry (its default), so the
ALLOWED call needs MySQL running. The BLOCKED call is rejected by the
safety rule before ever touching the database (see execute_tool.py's
_safety_violation check, called before with_retry/the tool itself), so
that half works even without MySQL running.

Usage (from the repo root; MySQL running for the allowed-call half):
    python scripts/demo_safety_rule_hw05.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "mcp_servers"))

from execute_tool import SAFETY_MAX_SEARCH_LIMIT, execute_tool  # noqa: E402


def main() -> None:
    print(f"Safety rule: search_recalls limit must be <= {SAFETY_MAX_SEARCH_LIMIT} per call\n")

    print(f"=== Allowed call: search_recalls(query='a', limit=10) ===")
    raw = execute_tool("search_recalls", {"query": "a", "limit": 10})
    result = json.loads(raw)
    print(json.dumps(result, indent=2)[:600])
    assert result["ok"] is True, "expected the allowed call to succeed (is MySQL running?)"
    print("ALLOWED as expected\n")

    print(f"=== Blocked call: search_recalls(query='a', limit=50)  (> {SAFETY_MAX_SEARCH_LIMIT}) ===")
    raw = execute_tool("search_recalls", {"query": "a", "limit": 50})
    result = json.loads(raw)
    print(json.dumps(result, indent=2))
    assert result["ok"] is False and "safety rule violated" in result["error"]
    print("BLOCKED as expected (ok=false, no exception raised)")


if __name__ == "__main__":
    main()
