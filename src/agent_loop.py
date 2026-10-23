"""HW7 Part 2: a hand-written agent loop on the HW1 model adapter.

``run_agent(user_input, ...)`` asks the model (through ``OllamaModelClient.complete``) what to do, runs
the tool calls it makes through the HW5 ``execute_tool`` safe entry point, appends each result to the
conversation as a ``role: "tool"`` message, and repeats until the model gives a final answer or a hard
iteration ceiling is reached. It never raises: every way a run can end is a ``stop_reason`` in the
returned record.

Repair path. Before a tool call is executed it is checked: known tool? arguments a JSON object? do they
satisfy the tool's JSON schema (required, types, ranges)? If not, the call is NOT executed; the model gets
a tool message naming the specific problem and one more chance. The same happens when the model answers
in plain text although the task needs tools ("text_instead_of_tool") or answers before it has made the
required number of tool calls ("lost_chain"). Each failure situation gets at most ``max_failed_repairs``
failed repair attempts, then the run stops cleanly with ``stop_reason="repair_exhausted"``.

Every failure is recorded in ``events`` with one of four classes: malformed_arguments, unknown_tool,
text_instead_of_tool, lost_chain, and whether a later turn repaired it. That is what the reliability
measurement (well-formed rate before / after repair) is computed from.
"""
from __future__ import annotations

import json
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent

FAILURE_CLASSES = ("malformed_arguments", "unknown_tool", "text_instead_of_tool", "lost_chain")
STOP_REASONS = ("final_answer", "max_iterations", "repair_exhausted", "model_error", "tool_budget", "token_budget")

DEFAULT_SYSTEM_PROMPT = (
    "You are an assistant for a grocery recall database. Use the provided tools to look things up. "
    "Never invent record IDs, counts, units or product names: take them from tool results. "
    "Call tools step by step; when a call needs a value from an earlier result, wait for that result first. "
    "If a tool returns an error, read the message and either fix the call or tell the user what went wrong. "
    "When you have what you need, answer briefly using only what the tools returned."
)

# The three HW5 domain tools, as plain {name, description, parameters} schemas. limit <= 25 matches the HW5
# safety rule in execute_tool (SAFETY_MAX_SEARCH_LIMIT).
RECALL_TOOL_SCHEMAS: List[dict] = [
    {
        "name": "search_recalls",
        "description": ("Search recall records by product or brand name (case-insensitive substring). Returns "
                        "matching records ordered by id; each has id, product_name, brand_name, record_code, "
                        "units_affected, source_id."),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "minLength": 1, "description": "text to look for in the product or brand name"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 25, "description": "maximum number of records (default 10)"},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    {
        "name": "recall_detail",
        "description": "Get the full details of ONE recall record by its integer id.",
        "parameters": {
            "type": "object",
            "properties": {"record_id": {"type": "integer", "minimum": 1, "description": "the record's id"}},
            "required": ["record_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "source_recall_summary",
        "description": ("Aggregate for one reporting source: how many recall records it filed and the total units "
                        "affected, by integer source id."),
        "parameters": {
            "type": "object",
            "properties": {"source_id": {"type": "integer", "minimum": 1, "description": "the source's id"}},
            "required": ["source_id"],
            "additionalProperties": False,
        },
    },
]


def to_ollama_tools(schemas: Sequence[Mapping[str, Any]]) -> List[dict]:
    """{name, description, parameters} -> the {"type": "function", "function": {...}} shape Ollama expects."""
    return [{"type": "function", "function": dict(s)} for s in schemas]


# --- argument validation (a small JSON-Schema subset: type, required, enum, min/max, minLength) -----------

def _type_ok(value: Any, expected: str) -> bool:
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    py = {"string": str, "boolean": bool, "object": dict, "array": list}.get(expected)
    return py is None or isinstance(value, py)


def _show(value: Any) -> str:
    text = repr(value)
    return text if len(text) <= 40 else text[:37] + "..."


def validate_args(parameters: Mapping[str, Any], args: Any) -> List[str]:
    """Return a list of specific problems with ``args`` (empty list = valid)."""
    if not isinstance(args, dict):
        return [f"arguments must be a JSON object, got {type(args).__name__}"]
    props = parameters.get("properties", {})
    problems: List[str] = []
    for name in parameters.get("required", []):
        if name not in args:
            problems.append(f"missing required argument '{name}'")
    for name, value in args.items():
        spec = props.get(name)
        if spec is None:
            if parameters.get("additionalProperties") is False:
                problems.append(f"unexpected argument '{name}' (allowed: {', '.join(sorted(props)) or 'none'})")
            continue
        expected = spec.get("type")
        if expected and not _type_ok(value, expected):
            problems.append(f"argument '{name}' must be {expected}, got {type(value).__name__} {_show(value)}")
            continue
        if "enum" in spec and value not in spec["enum"]:
            problems.append(f"argument '{name}' must be one of {spec['enum']}, got {_show(value)}")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if "minimum" in spec and value < spec["minimum"]:
                problems.append(f"argument '{name}' must be >= {spec['minimum']}, got {value}")
            if "maximum" in spec and value > spec["maximum"]:
                problems.append(f"argument '{name}' must be <= {spec['maximum']}, got {value}")
        if isinstance(value, str) and "minLength" in spec and len(value.strip()) < spec["minLength"]:
            problems.append(f"argument '{name}' must not be empty")
    return problems


# --- helpers ---------------------------------------------------------------------------------------------

MAX_RECORDS_FED_BACK = 5


def _compact_for_model(result: dict, limit: int = MAX_RECORDS_FED_BACK) -> dict:
    """Keep the model's context small: at most ``limit`` list items go back, with a note saying how many.
    The FULL result is what the run record keeps."""
    data = result.get("data")
    if isinstance(data, list) and len(data) > limit:
        return {**result, "data": data[:limit], "note": f"showing {limit} of {len(data)} records"}
    return result


def _extract_calls(message: Mapping[str, Any]) -> List[dict]:
    """Normalise ``message.tool_calls`` into [{name, arguments, problem, raw}]."""
    calls: List[dict] = []
    for tc in message.get("tool_calls") or []:
        fn = tc.get("function") if isinstance(tc, Mapping) else None
        if not isinstance(fn, Mapping):
            calls.append({"name": None, "arguments": None, "problem": "tool call has no function object", "raw": tc})
            continue
        args, problem = fn.get("arguments"), None
        if isinstance(args, str):  # some models send the arguments as a JSON string
            try:
                args = json.loads(args) if args.strip() else {}
            except json.JSONDecodeError as exc:
                args, problem = None, f"arguments are not valid JSON ({exc.msg})"
        elif args is None:
            args = {}
        calls.append({"name": fn.get("name"), "arguments": args, "problem": problem, "raw": tc})
    return calls


def _looks_like_text_call(content: str, names: Sequence[str]) -> bool:
    """True if the reply spells a tool call out as text instead of using the tool-call mechanism."""
    if not content:
        return False
    for n in names:
        if re.search(rf'"(?:name|tool)"\s*:\s*"{re.escape(n)}"', content) or re.search(rf"\b{re.escape(n)}\s*\(", content):
            return True
    return False


def _summary(result: Mapping[str, Any]) -> str:
    if result.get("ok"):
        data = result.get("data")
        return f"ok ({len(data)} records)" if isinstance(data, list) else "ok"
    return f"ERROR: {result.get('error')}"


def default_recall_execute() -> Callable[[str, dict], str]:
    """The real HW5 wiring: execute_tool over the database-backed domain tools (needs MySQL)."""
    sys.path.insert(0, str(REPO_ROOT / "mcp_servers"))
    from execute_tool import execute_tool  # noqa: PLC0415

    return lambda name, args: execute_tool(name, args)


# --- the loop --------------------------------------------------------------------------------------------

def run_agent(
    user_input: str,
    *,
    client: Any,
    tool_schemas: Sequence[Mapping[str, Any]] = RECALL_TOOL_SCHEMAS,
    execute: Optional[Callable[[str, dict], str]] = None,
    system_prompt: str = DEFAULT_SYSTEM_PROMPT,
    min_tool_calls: int = 0,
    max_iterations: int = 8,
    max_failed_repairs: int = 2,
    max_tool_calls: Optional[int] = None,
    max_total_tokens: Optional[int] = None,
    temperature: float = 0.0,
    log: Optional[Callable[[str], None]] = print,
    log_path: Optional[Path] = None,
    case_id: Optional[str] = None,
) -> dict:
    """Run the agent on one request and return a run record. Never raises.

    min_tool_calls  the task needs at least this many valid tool calls before an answer is accepted
                    (0 = no requirement). Used to detect text_instead_of_tool and lost_chain.
    max_iterations  hard ceiling on model calls.
    max_failed_repairs  failed repair attempts tolerated per failure situation before stopping.
    max_tool_calls / max_total_tokens  optional hard budgets (used by the Reflexion wrapper): no tool call is
                    executed past the first, and no new model call is made past the second; the run ends with
                    stop_reason "tool_budget" / "token_budget".
    """
    say = log or (lambda _msg: None)
    execute = execute or default_recall_execute()
    schemas = {s["name"]: s for s in tool_schemas}
    tools_payload = to_ollama_tools(tool_schemas)

    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_input},
    ]
    started = time.perf_counter()
    events: List[dict] = []
    invocations: List[dict] = []
    emitted = invalid = repairs_used = 0
    input_tokens = output_tokens = 0
    model_ms = 0.0
    streak = 0                  # consecutive failing turns in the current failure situation
    open_events: List[dict] = []  # events of the current situation, marked repaired once a turn succeeds
    final_text: Optional[str] = None
    stop_reason: Optional[str] = None
    error: Optional[str] = None
    iteration = 0

    def valid_calls() -> int:
        return len(invocations)

    def fail_turn(iteration: int, cls: str, detail: str, **extra: Any) -> None:
        ev = {"iteration": iteration, "class": cls, "detail": detail, "repaired": False, **extra}
        events.append(ev)
        open_events.append(ev)
        say(f"[repair] iteration {iteration}: {cls} - {detail}")

    for iteration in range(1, max_iterations + 1):
        if max_total_tokens is not None and input_tokens + output_tokens >= max_total_tokens:
            stop_reason = "token_budget"
            say(f"[stop] token budget of {max_total_tokens} reached")
            break
        t0 = time.perf_counter()
        try:
            resp = client.complete(messages, tools=tools_payload, temperature=temperature)
        except Exception as exc:  # noqa: BLE001 - any adapter failure is a clean stop, not a crash
            stop_reason, error = "model_error", f"{type(exc).__name__}: {exc}"
            say(f"[error] model call failed: {error}")
            break
        model_ms += (time.perf_counter() - t0) * 1000.0
        input_tokens += int(getattr(resp, "input_tokens", 0) or 0)
        output_tokens += int(getattr(resp, "output_tokens", 0) or 0)

        raw_message = (getattr(resp, "raw", None) or {}).get("message") or {}
        content = getattr(resp, "content", "") or ""
        calls = _extract_calls(raw_message)
        turn_failed = False

        if calls:
            messages.append({"role": "assistant", "content": content,
                             "tool_calls": [c["raw"] for c in calls]})
            for call in calls:
                if max_tool_calls is not None and len(invocations) >= max_tool_calls:
                    stop_reason = "tool_budget"
                    say(f"[stop] tool-call budget of {max_tool_calls} reached")
                    break
                emitted += 1
                name, args = call["name"], call["arguments"]
                problem = call["problem"]
                cls = "malformed_arguments"
                if problem is None and name not in schemas:
                    problem, cls = (f"unknown tool {name!r}; the available tools are: {', '.join(schemas)}",
                                    "unknown_tool")
                if problem is None:
                    issues = validate_args(schemas[name]["parameters"], args)
                    if issues:
                        problem = "; ".join(issues)
                if problem is not None:
                    invalid += 1
                    turn_failed = True
                    fail_turn(iteration, cls, problem, tool=name, arguments=args)
                    messages.append({"role": "tool", "tool_name": str(name or "unknown"), "content": json.dumps(
                        {"ok": False, "data": None, "error": f"invalid tool call, not executed: {problem}. "
                         "Fix the call and try again."})})
                    continue
                try:
                    result = json.loads(execute(name, args))
                except Exception as exc:  # noqa: BLE001 - execute_tool should not raise; belt and braces
                    result = {"ok": False, "data": None, "error": f"tool execution failed: {exc}"}
                invocations.append({"n": len(invocations) + 1, "iteration": iteration, "tool": name,
                                    "arguments": args, "ok": bool(result.get("ok")), "error": result.get("error"),
                                    "result": result})
                say(f"[tool {len(invocations)}] {name} {json.dumps(args, ensure_ascii=False)} -> {_summary(result)}")
                messages.append({"role": "tool", "tool_name": name,
                                 "content": json.dumps(_compact_for_model(result), ensure_ascii=False)})
        else:
            messages.append({"role": "assistant", "content": content})
            if valid_calls() < min_tool_calls:
                turn_failed = True
                if valid_calls() == 0:
                    detail = ("replied with text but this task needs tools"
                              + (" (the reply spells a tool call out as text)" if _looks_like_text_call(content, list(schemas)) else ""))
                    fail_turn(iteration, "text_instead_of_tool", detail)
                    nudge = ("Your last reply did not call a tool. This task requires looking things up with the "
                             "available tools. Call the appropriate tool now using the tool-calling mechanism, "
                             "not text.")
                else:
                    detail = f"answered after {valid_calls()} tool call(s) but the task needs at least {min_tool_calls}"
                    fail_turn(iteration, "lost_chain", detail)
                    nudge = (f"You have made {valid_calls()} tool call(s) but this task needs at least "
                             f"{min_tool_calls} steps. Do not answer yet: call the next tool you need.")
                messages.append({"role": "user", "content": nudge})
            else:
                final_text, stop_reason = content.strip(), "final_answer"

        if stop_reason == "tool_budget":
            break
        if turn_failed:
            streak += 1
            if streak > max_failed_repairs:
                stop_reason = "repair_exhausted"
                say(f"[stop] repair failed {max_failed_repairs} times; giving up cleanly")
                break
            repairs_used += 1
        else:
            for ev in open_events:
                ev["repaired"] = True
            open_events.clear()
            streak = 0
        if stop_reason == "final_answer":
            break
    else:
        stop_reason = "max_iterations"

    if stop_reason is None:  # loop ended by break without a reason: cannot happen, but keep the record honest
        stop_reason = "max_iterations"

    record = {
        "run_id": uuid.uuid4().hex[:8],
        "case_id": case_id,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "model": getattr(client, "model", None),
        "temperature": temperature,
        "user_input": user_input,
        "min_tool_calls": min_tool_calls,
        "max_iterations": max_iterations,
        "stop_reason": stop_reason,
        "error": error,
        "final_text": final_text,
        "iterations": iteration,
        "total_tool_calls": len(invocations),
        "emitted_calls": emitted,
        "invalid_calls": invalid,
        "repair_reprompts": repairs_used,
        "tool_calls": invocations,
        "events": events,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "model_latency_ms": round(model_ms, 1),
        "wall_ms": round((time.perf_counter() - started) * 1000.0, 1),
        "messages": messages,
    }
    say(f"[done] stop_reason={stop_reason} total_tool_calls={len(invocations)} invalid_calls={invalid} "
        f"repair_reprompts={repairs_used} tokens={input_tokens}+{output_tokens}")
    if log_path:
        path = Path(log_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record
