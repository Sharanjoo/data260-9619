"""HW5 Part 5.II: Ollama-based agent loop over the three domain tools,
driven exclusively through Part 4's execute_tool() (never the tools
directly, and never domain_tools.py directly).

Design: a simple ReAct-style loop. Each turn, the model sees the system
prompt (tool descriptions + the required one-JSON-object-per-turn reply
shape), the user's request, and the transcript so far (including previous
tool results), and must reply with exactly one JSON object of one of two
shapes:

    {"action": "call_tool", "tool": "<name>", "inputs": {...}}
    {"action": "final_answer", "text": "<answer for the user>"}

run_agent(user_input) drives this loop, calling execute_tool(...) for
every call_tool action and feeding the {ok, data, error} result back to
the model as the next turn's context. A turn counter enforces max_steps:
if the model never produces a final_answer (or a tool call is blocked by
Part 5.I's safety rule) within max_steps turns, the loop stops anyway --
"a clean error result instead of crashing" applies here too, at the agent
level. Every step (tool call, input, result) and the run's final stop
reason are appended as one JSON line to agent_runs.jsonl.

Model interface (dependency injection, same pattern as execute_tool's
`tools=`): anything with a `.generate(messages) -> str` method works.
OllamaModel wraps the local `ollama` Python package for real runs.
MockModel is a deterministic, offline, no-network test double -- used by
the two Part 5.III tests (offline, no live model) and nowhere else.
"""
from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from execute_tool import execute_tool  # noqa: E402

DEFAULT_LOG_PATH = (
    Path(__file__).resolve().parent.parent / "reports" / "hw05" / "raw" / "agent_runs.jsonl"
)

SYSTEM_PROMPT = """You are an assistant for a grocery recall database. You can call three tools:

- search_recalls(query: str, limit: int = 10): search recall records by product or brand name substring.
- recall_detail(record_id: int): get the full details of one recall record by id.
- source_recall_summary(source_id: int): get the record count and total units affected for one reporting source.

Respond with EXACTLY ONE JSON object per turn, and nothing else -- no other text, no markdown fences:
  {"action": "call_tool", "tool": "<tool name>", "inputs": {<arguments>}}
  {"action": "final_answer", "text": "<your answer to the user>"}

Use call_tool to gather the information you need, then respond with final_answer once you can \
answer the user's request (or once you've determined you cannot)."""


class OllamaModel:
    """Thin wrapper around the local Ollama server's chat API. Requires
    `pip install ollama` and a running local Ollama server with the named
    model pulled (e.g. `ollama pull qwen3:8b`)."""

    def __init__(self, model_name: str = "qwen3:8b"):
        self.model_name = model_name

    def generate(self, messages: List[Dict[str, str]]) -> str:
        import ollama  # imported lazily so offline/MockModel usage never needs this installed

        response = ollama.chat(
            model=self.model_name, messages=messages, options={"temperature": 0}
        )
        return response["message"]["content"]


class MockModel:
    """Deterministic, fully offline test double -- no network, no live
    model. `responses` is a list of canned reply strings returned in
    order, one per call to generate(); once exhausted, the last response
    repeats. This is what lets a test force a specific agent trajectory
    (e.g. always call_tool, never final_answer, to deterministically
    reach max_steps) without any randomness or a real LLM."""

    def __init__(self, responses: List[str]):
        self.responses = responses
        self.calls = 0

    def generate(self, messages: List[Dict[str, str]]) -> str:
        idx = min(self.calls, len(self.responses) - 1)
        self.calls += 1
        return self.responses[idx]


def _parse_action(raw_reply: str) -> Optional[dict]:
    """Extract the single JSON action object from a model reply. Tolerates
    markdown code fences or surrounding prose by finding the first '{' and
    decoding from there; returns None (not raises) on anything unparsable,
    so a malformed reply is handled, not a crash."""
    text = raw_reply.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text[:4].lower() == "json":
            text = text[4:]
        text = text.strip()
    start = text.find("{")
    if start == -1:
        return None
    try:
        obj, _ = json.JSONDecoder().raw_decode(text[start:])
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        return None


def run_agent(
    user_input: str,
    *,
    model: Optional[Any] = None,
    tools: Optional[Dict[str, Callable[..., dict]]] = None,
    max_steps: int = 5,
    log_path: Optional[Path] = None,
) -> dict:
    """Run the agent loop for one user request. Always returns a run
    record (also appended to agent_runs.jsonl unless log_path=False) --
    never raises, and never calls a domain tool except through
    execute_tool().

    `model`: defaults to OllamaModel() (the real local model). Tests pass
    a MockModel instead.
    `tools`: passed straight through to every execute_tool() call --
    defaults to the real database-backed registry; tests pass a fake one,
    exactly like Part 4's tests.
    `log_path`: defaults to reports/hw05/raw/agent_runs.jsonl. Pass False
    to skip writing a log line at all (used by tests, so they never touch
    the filesystem's report folder).
    """
    model = model if model is not None else OllamaModel()
    if log_path is None:
        log_path = DEFAULT_LOG_PATH

    messages: List[Dict[str, str]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_input},
    ]

    run_id = uuid.uuid4().hex[:8]
    steps_log: List[dict] = []
    tool_call_count = 0
    final_text: Optional[str] = None
    stop_reason: Optional[str] = None

    for step in range(1, max_steps + 1):
        raw_reply = model.generate(messages)
        messages.append({"role": "assistant", "content": raw_reply})
        action = _parse_action(raw_reply)

        if action is None:
            steps_log.append({"step": step, "raw_reply": raw_reply, "parse_error": True})
            messages.append(
                {
                    "role": "user",
                    "content": "Your last reply was not valid JSON in the required shape. "
                    "Respond with exactly one JSON object: call_tool or final_answer.",
                }
            )
            continue

        action_type = action.get("action")

        if action_type == "final_answer":
            final_text = action.get("text", "")
            steps_log.append({"step": step, "action": "final_answer", "text": final_text})
            stop_reason = "normal_completion"
            break

        if action_type == "call_tool":
            tool_name = action.get("tool")
            tool_inputs = action.get("inputs", {}) or {}
            tool_call_count += 1
            raw_result = execute_tool(tool_name, tool_inputs, tools=tools)
            result = json.loads(raw_result)
            steps_log.append(
                {
                    "step": step,
                    "action": "call_tool",
                    "tool": tool_name,
                    "inputs": tool_inputs,
                    "result": result,
                }
            )

            if result.get("ok") is False and str(result.get("error", "")).startswith(
                "safety rule violated"
            ):
                stop_reason = "safety_rule_block"
                break

            messages.append({"role": "user", "content": f"Tool result: {json.dumps(result)}"})
            continue

        steps_log.append({"step": step, "raw_reply": raw_reply, "parse_error": True})
        messages.append(
            {"role": "user", "content": "Unrecognized action. Use call_tool or final_answer."}
        )

    if stop_reason is None:
        stop_reason = "max_steps"

    run_record = {
        "run_id": run_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "user_input": user_input,
        "max_steps": max_steps,
        "steps": steps_log,
        "step_count": len(steps_log),
        "tool_call_count": tool_call_count,
        "stop_reason": stop_reason,
        "final_text": final_text,
    }

    if log_path:
        log_path = Path(log_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a") as f:
            f.write(json.dumps(run_record) + "\n")

    return run_record
