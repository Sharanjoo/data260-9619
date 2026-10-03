"""HW5 Part 4.23/24: offline test suite for execute_tool().

Runs entirely offline -- no live database, no network, no LLM -- by
injecting a fake tool registry into execute_tool() via its `tools=`
parameter (dependency injection, per the spec). The fakes mirror the real
domain_tools.py validation logic and error strings closely (so these tests
exercise the exact rejected-call cases documented in
reports/hw05/part3_tool_contracts.md), but never touch MySQL.

Six tests total: one valid input + one invalid input for each of the three
domain tools. Prints PASS/FAIL per test and a final X/Y summary. Part 5
adds two more tests to this same file/pattern (safety-rule block,
MockModel max_steps) once those exist.

Usage:
    python scripts/test_execute_tool_hw05.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "mcp_servers"))

from execute_tool import execute_tool  # noqa: E402
from agent import MockModel, run_agent  # noqa: E402

# --- Fake tool registry: dependency injection, no DB involved at all ---


def fake_search_recalls(query: str, limit: int = 10) -> dict:
    if not isinstance(query, str) or not query.strip():
        return {"ok": False, "data": None, "error": "query must be a non-empty string"}
    if not isinstance(limit, int) or not (1 <= limit <= 100):
        return {"ok": False, "data": None, "error": "limit must be an integer between 1 and 100"}
    return {
        "ok": True,
        "data": [{"id": 1, "product_name": "Fake Product", "brand_name": "Fake Brand",
                   "record_code": "REC-FAKE01", "units_affected": 10}],
        "error": None,
    }


def fake_recall_detail(record_id) -> dict:
    try:
        record_id = int(record_id)
    except (TypeError, ValueError):
        return {"ok": False, "data": None, "error": "record_id must be an integer"}
    if record_id == 999999999:
        return {"ok": False, "data": None, "error": f"no recall record with id {record_id}"}
    return {
        "ok": True,
        "data": {"id": record_id, "product_name": "Fake Product", "brand_name": "Fake Brand"},
        "error": None,
    }


def fake_source_recall_summary(source_id) -> dict:
    try:
        source_id = int(source_id)
    except (TypeError, ValueError):
        return {"ok": False, "data": None, "error": "source_id must be an integer"}
    if source_id == 999999999:
        return {"ok": False, "data": None, "error": f"no recall source with id {source_id}"}
    return {
        "ok": True,
        "data": {"source_id": source_id, "source_name": "Fake Source",
                  "record_count": 3, "total_units_affected": 42},
        "error": None,
    }


FAKE_TOOLS = {
    "search_recalls": fake_search_recalls,
    "recall_detail": fake_recall_detail,
    "source_recall_summary": fake_source_recall_summary,
}


# --- Test runner ---

_results = []  # (name, passed: bool, detail: str)


def check(test_name: str, condition: bool, detail: str = "") -> None:
    _results.append((test_name, condition, detail))
    status = "PASS" if condition else "FAIL"
    suffix = f"  ({detail})" if detail and not condition else ""
    print(f"[{status}] {test_name}{suffix}")


def run_tests() -> None:
    # 1. search_recalls -- valid
    raw = execute_tool("search_recalls", {"query": "fake", "limit": 5}, tools=FAKE_TOOLS)
    result = json.loads(raw)
    check(
        "search_recalls: valid input returns ok=true with data",
        result["ok"] is True and isinstance(result["data"], list) and len(result["data"]) == 1,
        repr(result),
    )

    # 2. search_recalls -- invalid (empty query, from Part 3)
    raw = execute_tool("search_recalls", {"query": "", "limit": 5}, tools=FAKE_TOOLS)
    result = json.loads(raw)
    check(
        "search_recalls: empty query is rejected with ok=false",
        result["ok"] is False and result["error"] == "query must be a non-empty string",
        repr(result),
    )

    # 3. recall_detail -- valid
    raw = execute_tool("recall_detail", {"record_id": 42}, tools=FAKE_TOOLS)
    result = json.loads(raw)
    check(
        "recall_detail: valid id returns ok=true with matching data",
        result["ok"] is True and result["data"]["id"] == 42,
        repr(result),
    )

    # 4. recall_detail -- invalid (non-existent id, from Part 3)
    raw = execute_tool("recall_detail", {"record_id": 999999999}, tools=FAKE_TOOLS)
    result = json.loads(raw)
    check(
        "recall_detail: non-existent id is rejected with ok=false",
        result["ok"] is False and result["error"] == "no recall record with id 999999999",
        repr(result),
    )

    # 5. source_recall_summary -- valid
    raw = execute_tool("source_recall_summary", {"source_id": 7}, tools=FAKE_TOOLS)
    result = json.loads(raw)
    check(
        "source_recall_summary: valid id returns ok=true with aggregate data",
        result["ok"] is True and result["data"]["record_count"] == 3,
        repr(result),
    )

    # 6. source_recall_summary -- invalid (non-existent id, from Part 3)
    raw = execute_tool("source_recall_summary", {"source_id": 999999999}, tools=FAKE_TOOLS)
    result = json.loads(raw)
    check(
        "source_recall_summary: non-existent id is rejected with ok=false",
        result["ok"] is False and result["error"] == "no recall source with id 999999999",
        repr(result),
    )

    # Bonus: execute_tool's own safety net -- unknown tool name never crashes
    raw = execute_tool("not_a_real_tool", {}, tools=FAKE_TOOLS)
    result = json.loads(raw)
    check(
        "execute_tool: unknown tool name returns ok=false instead of raising",
        result["ok"] is False and "unknown tool" in result["error"],
        repr(result),
    )

    # 8. Part 5.III test #1: execute_tool blocks a call that violates the
    # safety rule (search_recalls limit over SAFETY_MAX_SEARCH_LIMIT=25).
    # Pure execute_tool-level test -- no agent loop involved.
    raw = execute_tool("search_recalls", {"query": "a", "limit": 50}, tools=FAKE_TOOLS)
    result = json.loads(raw)
    check(
        "execute_tool: safety rule blocks search_recalls limit=50 with ok=false",
        result["ok"] is False and "safety rule violated" in result["error"],
        repr(result),
    )

    # 9. Part 5.III test #2: run_agent, using MockModel, stops after
    # reaching max_steps. MockModel always replies with a call_tool action
    # and never a final_answer, so the loop can only stop by exhausting
    # its step budget. Fully offline: MockModel (no live model, no
    # network) + FAKE_TOOLS (no database) + log_path=False (no filesystem
    # write into the real report folder).
    always_calls_tool = MockModel(
        [json.dumps({"action": "call_tool", "tool": "search_recalls", "inputs": {"query": "a", "limit": 5}})]
    )
    run = run_agent(
        "keep searching forever",
        model=always_calls_tool,
        tools=FAKE_TOOLS,
        max_steps=3,
        log_path=False,
    )
    check(
        "run_agent: MockModel that never finishes stops at max_steps",
        run["stop_reason"] == "max_steps" and run["step_count"] == 3,
        repr({"stop_reason": run["stop_reason"], "step_count": run["step_count"]}),
    )

    passed = sum(1 for _, ok, _ in _results if ok)
    total = len(_results)
    print(f"\n{passed}/{total} tests passed")
    if passed != total:
        sys.exit(1)


if __name__ == "__main__":
    run_tests()
