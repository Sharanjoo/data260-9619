"""Offline checks for src/agent_loop.py (HW7 Part 2). No Ollama, no database: a scripted fake model
and an in-memory tool executor. Run: python scripts/test_agent_loop_hw07.py"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.agent_loop import RECALL_TOOL_SCHEMAS, run_agent, validate_args  # noqa: E402

PASSED = FAILED = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASSED, FAILED
    if cond:
        PASSED += 1
    else:
        FAILED += 1
        print(f"FAIL: {name} {detail}")


def tc(name, args):
    return {"function": {"name": name, "arguments": args}}


def reply(text="", calls=None):
    msg = {"role": "assistant", "content": text}
    if calls:
        msg["tool_calls"] = calls
    return SimpleNamespace(content=text, input_tokens=10, output_tokens=5, total_tokens=15,
                           model="fake", total_duration_ns=0, raw={"message": msg})


class FakeClient:
    model = "fake"

    def __init__(self, script):
        self.script, self.seen = list(script), []

    def complete(self, messages, tools=None, *, temperature=0.0, response_format=None):
        self.seen.append([dict(m) for m in messages])
        if not self.script:
            raise RuntimeError("script exhausted")
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


RECORDS = {1: {"id": 1, "product_name": "Peanut Butter", "units_affected": 100},
           2: {"id": 2, "product_name": "Almond Milk", "units_affected": 40}}


def execute(name, args):
    if name == "search_recalls":
        q = args["query"].lower()
        return json.dumps({"ok": True, "data": [r for r in RECORDS.values() if q in r["product_name"].lower()], "error": None})
    if name == "recall_detail":
        r = RECORDS.get(args["record_id"])
        return json.dumps({"ok": r is not None, "data": r, "error": None if r else f"no recall record with id {args['record_id']}"})
    return json.dumps({"ok": True, "data": {"source_id": args["source_id"], "record_count": 2}, "error": None})


def run(script, **kw):
    kw.setdefault("log", None)
    return run_agent("question", client=FakeClient(script), execute=execute, **kw)


# --- validate_args ---
P = RECALL_TOOL_SCHEMAS[0]["parameters"]
check("valid args", validate_args(P, {"query": "milk", "limit": 5}) == [])
check("missing required", "missing required argument 'query'" in validate_args(P, {})[0])
check("wrong type", "must be integer" in validate_args(P, {"query": "m", "limit": "5"})[0])
check("bool is not integer", "must be integer" in validate_args(P, {"query": "m", "limit": True})[0])
check("max", "<= 25" in validate_args(P, {"query": "m", "limit": 99})[0])
check("empty string", "must not be empty" in validate_args(P, {"query": "  "})[0])
check("extra arg", "unexpected argument" in validate_args(P, {"query": "m", "foo": 1})[0])
check("non-object", "JSON object" in validate_args(P, "milk")[0])

# --- clean two-step chain ---
r = run([reply(calls=[tc("search_recalls", {"query": "peanut"})]),
         reply(calls=[tc("recall_detail", {"record_id": 1})]),
         reply("Peanut Butter, 100 units.")], min_tool_calls=2)
check("clean: final_answer", r["stop_reason"] == "final_answer", r["stop_reason"])
check("clean: 2 calls", r["total_tool_calls"] == 2 and r["invalid_calls"] == 0 and r["events"] == [])
check("clean: tool-role messages", sum(m["role"] == "tool" for m in r["messages"]) == 2)
check("clean: tokens summed", r["input_tokens"] == 30 and r["output_tokens"] == 15)

# --- malformed args, repaired ---
c = FakeClient([reply(calls=[tc("recall_detail", {"record_id": "one"})]),
                reply(calls=[tc("recall_detail", {"record_id": 1})]), reply("done")])
r = run_agent("q", client=c, execute=execute, log=None, min_tool_calls=1)
check("repair: final", r["stop_reason"] == "final_answer")
check("repair: class", r["events"][0]["class"] == "malformed_arguments" and r["events"][0]["repaired"] is True)
check("repair: 1 reprompt, 1 invalid, 1 valid call", (r["repair_reprompts"], r["invalid_calls"], r["total_tool_calls"]) == (1, 1, 1))
tool_msg = [m for m in c.seen[1] if m["role"] == "tool"][0]["content"]
check("repair: specific problem sent back", "record_id" in tool_msg and "integer" in tool_msg and "not executed" in tool_msg)

# --- unknown tool ---
r = run([reply(calls=[tc("delete_everything", {})]), reply(calls=[tc("recall_detail", {"record_id": 2})]), reply("ok")], min_tool_calls=1)
check("unknown tool", r["events"][0]["class"] == "unknown_tool" and r["events"][0]["repaired"] and r["stop_reason"] == "final_answer")

# --- arguments as invalid JSON string / as JSON string ---
r = run([reply(calls=[tc("recall_detail", "{record_id: 1")]), reply(calls=[tc("recall_detail", '{"record_id": 1}')]), reply("ok")], min_tool_calls=1)
check("bad JSON string args", r["events"][0]["class"] == "malformed_arguments" and r["total_tool_calls"] == 1)

# --- text instead of tool ---
r = run([reply('{"name": "search_recalls", "arguments": {"query": "x"}}'), reply(calls=[tc("search_recalls", {"query": "milk"})]), reply("ok")], min_tool_calls=1)
check("text_instead_of_tool", r["events"][0]["class"] == "text_instead_of_tool" and "spells" in r["events"][0]["detail"] and r["events"][0]["repaired"])

# --- lost chain ---
r = run([reply(calls=[tc("search_recalls", {"query": "milk"})]), reply("Almond Milk is affected."),
         reply(calls=[tc("recall_detail", {"record_id": 2})]), reply("Almond Milk, 40 units.")], min_tool_calls=2)
check("lost_chain", r["events"][0]["class"] == "lost_chain" and r["events"][0]["repaired"] and r["total_tool_calls"] == 2)

# --- repair exhausted (bounded) ---
bad = lambda: reply(calls=[tc("recall_detail", {})])  # noqa: E731
r = run([bad() for _ in range(10)], min_tool_calls=1, max_failed_repairs=2)
check("exhausted: stop", r["stop_reason"] == "repair_exhausted", r["stop_reason"])
check("exhausted: bounded", r["iterations"] == 3 and r["repair_reprompts"] == 2 and all(not e["repaired"] for e in r["events"]))

# --- max iterations ---
r = run([reply(calls=[tc("search_recalls", {"query": "m"})]) for _ in range(10)], max_iterations=3)
check("max_iterations", r["stop_reason"] == "max_iterations" and r["iterations"] == 3 and r["total_tool_calls"] == 3)

# --- model error ---
r = run([RuntimeError("boom")])
check("model_error", r["stop_reason"] == "model_error" and "boom" in r["error"])

# --- tool error is fed back, not a repair; error recovery ---
r = run([reply(calls=[tc("recall_detail", {"record_id": 999})]), reply(calls=[tc("search_recalls", {"query": "peanut"})]),
         reply("Record 999 does not exist; I found Peanut Butter (id 1) instead.")], min_tool_calls=1)
check("tool error: not counted invalid", r["invalid_calls"] == 0 and r["repair_reprompts"] == 0)
check("tool error: recorded", r["tool_calls"][0]["ok"] is False and "no recall record" in r["tool_calls"][0]["error"])
check("tool error: run continues", r["stop_reason"] == "final_answer" and r["total_tool_calls"] == 2)

# --- no required calls: plain answer is fine ---
r = run([reply("Hello!")])
check("no tools needed", r["stop_reason"] == "final_answer" and r["total_tool_calls"] == 0 and r["events"] == [])

# --- big lists are trimmed for the model but kept in the record ---
big = lambda n, a: json.dumps({"ok": True, "data": [{"id": i} for i in range(20)], "error": None})  # noqa: E731
c = FakeClient([reply(calls=[tc("search_recalls", {"query": "m"})]), reply("ok")])
r = run_agent("q", client=c, execute=big, log=None)
check("trim: model sees 5", len(json.loads([m for m in c.seen[1] if m["role"] == "tool"][0]["content"])["data"]) == 5)
check("trim: record keeps 20", len(r["tool_calls"][0]["result"]["data"]) == 20)

# --- log file ---
import tempfile  # noqa: E402

with tempfile.TemporaryDirectory() as d:
    p = Path(d) / "sub" / "runs.jsonl"
    run([reply("hi")], log_path=p, case_id="t1")
    rec = json.loads(p.read_text().splitlines()[0])
    check("log file", rec["case_id"] == "t1" and rec["stop_reason"] == "final_answer")

print(f"{PASSED} checks passed, {FAILED} failed")
sys.exit(1 if FAILED else 0)
