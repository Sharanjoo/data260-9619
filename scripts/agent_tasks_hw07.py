"""The fixed HW7 Part 2 cases (A, B, C, error recovery) and their verifiers.

Ground truth is computed from the database through the same HW5 domain tools the agent uses, and is
compared against the agent's final answer (not against what the agent's tool calls returned), so a
confident but wrong answer fails.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Callable, Dict, List, Tuple

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "mcp_servers"))
os.environ.setdefault("MYSQL_PORT", "43306")

STUDENT_BANNER = "Student: Sharan Lourduraj (SJSU 018169619)  PREFIX s9619  DOMAIN_ID 3 (grocery recall notices)"

TASKS: Dict[str, dict] = {
    "A": {
        "title": "search term, then detail lookup of the first result",
        "prompt": ("Search the recalls for 'Farmstead Yogurt' and give me the full details of the first result: "
                   "its record id, record code, brand name and the name of the source that filed it."),
        "min_tool_calls": 2,
    },
    "B": {
        "title": "aggregate question, then one supporting example",
        "prompt": ("How many recall records has source 611 filed in total? Then give one supporting example: "
                   "the product name and record code of recall record 15013."),
        "min_tool_calls": 2,
    },
    "C": {
        "title": "compare two entities (two searches + two detail lookups)",
        "prompt": ("Compare the first 'Farmstead Yogurt' recall with the first 'Deluxe Bottled Juice' recall. "
                   "Look up each one's full details, then tell me which of the two has the smaller record id "
                   "and give each one's record code and source name."),
        "min_tool_calls": 4,
    },
    "D": {
        "title": "error recovery: nonexistent record id",
        "prompt": "Show me the full details of recall record 999999.",
        "min_tool_calls": 1,
    },
}


def _tools():
    import domain_tools  # noqa: PLC0415 - needs MYSQL_PORT set first

    return domain_tools


def _first(query: str) -> dict:
    res = _tools().search_recalls(query, 1)
    if not (res["ok"] and res["data"]):
        raise RuntimeError(f"ground truth: no recall matches {query!r}")
    return res["data"][0]


def _has(text: str, needle) -> bool:
    return str(needle).lower() in text.lower()


def _has_number(text: str, number: int) -> bool:
    return re.search(rf"(?<![\d,]){number}(?![\d])", text.replace(",", "")) is not None


def expected_for(task_id: str) -> dict:
    t = _tools()
    if task_id == "A":
        rec = t.recall_detail(_first("Farmstead Yogurt")["id"])["data"]
        return {"id": rec["id"], "record_code": rec["record_code"], "brand_name": rec["brand_name"],
                "source_name": rec["source_name"]}
    if task_id == "B":
        summ = t.source_recall_summary(611)["data"]
        rec = t.recall_detail(15013)["data"]
        return {"record_count": summ["record_count"], "product_name": rec["product_name"],
                "record_code": rec["record_code"]}
    if task_id == "C":
        a = t.recall_detail(_first("Farmstead Yogurt")["id"])["data"]
        b = t.recall_detail(_first("Deluxe Bottled Juice")["id"])["data"]
        return {"ids": [a["id"], b["id"]], "smaller_id": min(a["id"], b["id"]),
                "record_codes": [a["record_code"], b["record_code"]],
                "source_names": [a["source_name"], b["source_name"]]}
    if task_id == "D":
        return {"phrases": ["not found", "no recall", "does not exist", "doesn't exist", "no record",
                            "could not find", "couldn't find", "not exist", "no such", "unable to find",
                            "not available", "can't find", "cannot find"]}
    raise KeyError(task_id)


def verify(task_id: str, record: dict, expected: dict) -> Tuple[bool, List[str]]:
    """Return (passed, problems). Also requires the run to have ended in a final answer."""
    problems: List[str] = []
    text = record.get("final_text") or ""
    if record.get("stop_reason") != "final_answer":
        problems.append(f"run did not finish with an answer (stop_reason={record.get('stop_reason')})")
        return False, problems
    if task_id == "A":
        for key in ("record_code", "source_name"):
            if not _has(text, expected[key]):
                problems.append(f"answer lacks {key} {expected[key]!r}")
        if not _has_number(text, expected["id"]):
            problems.append(f"answer lacks record id {expected['id']}")
    elif task_id == "B":
        if not _has_number(text, expected["record_count"]):
            problems.append(f"answer lacks record count {expected['record_count']}")
        for key in ("product_name", "record_code"):
            if not _has(text, expected[key]):
                problems.append(f"answer lacks {key} {expected[key]!r}")
    elif task_id == "C":
        for code in expected["record_codes"]:
            if not _has(text, code):
                problems.append(f"answer lacks record code {code!r}")
        for name in expected["source_names"]:
            if not _has(text, name):
                problems.append(f"answer lacks source name {name!r}")
        if not _has_number(text, expected["smaller_id"]):
            problems.append(f"answer does not name the smaller id {expected['smaller_id']}")
    elif task_id == "D":
        if not any(_has(text, p) for p in expected["phrases"]):
            problems.append("answer does not say the record was not found")
        calls = record.get("tool_calls") or []
        if not calls or calls[0].get("ok") is not False:
            problems.append("the lookup did not return the expected error")
        if re.search(r"record_code|brand_name|units_affected|SRC-", text):
            problems.append("answer contains record fields that cannot exist (possible invention)")
    return (not problems), problems


def run_case(task_id: str, *, client, temperature: float = 0.0, log: Callable = print, log_path=None,
             max_iterations: int = 8, execute=None) -> dict:
    from src.agent_loop import run_agent  # noqa: PLC0415

    spec = TASKS[task_id]
    rec = run_agent(spec["prompt"], client=client, execute=execute, min_tool_calls=spec["min_tool_calls"],
                    temperature=temperature, log=log, log_path=log_path, case_id=task_id,
                    max_iterations=max_iterations)
    expected = expected_for(task_id)
    ok, problems = verify(task_id, rec, expected)
    rec["expected"], rec["answer_correct"], rec["verifier_problems"] = expected, ok, problems
    return rec
