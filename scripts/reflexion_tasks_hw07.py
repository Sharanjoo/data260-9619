"""HW7 Part 3: the per-task verifiers used by Reflexion (and to score the original Part 2 runs).

verify_task(task_id, record, expected) -> {"ok", "problems": [{"rule", "detail"}], "content_ok", "process_ok",
                                           "unsupported_claims": [...]}
It is deterministic and uses no model. Three kinds of rule, each reported by name:
  answer_content      the final answer must contain the ground-truth values (agent_tasks_hw07.verify)
  required_lookup     the tool log must show the lookups the task asks for (process evidence)
  unsupported_claim   record codes, source names, lot names, 4+ digit ids and "N records" counts that appear in the
                      answer must also appear in the prompt or in a tool result of the same run
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))
from agent_tasks_hw07 import verify as content_verify  # noqa: E402

CODE_RE = re.compile(r"REC-\d+", re.I)
NAME_RE = re.compile(r"[A-Z][A-Za-z'&\-]*(?: [A-Za-z'&\-]+){0,5} #\d+")
LOT_RE = re.compile(r"\(Lot \d+\)", re.I)
BIG_NUM_RE = re.compile(r"(?<![\w#-])\d{4,}(?![\w-])")
COUNT_RE = re.compile(r"\b(\d+)\s+(?:recall\s+)?records?\b", re.I)


def evidence_text(record: dict) -> str:
    parts = [record.get("user_input") or ""]
    parts += [json.dumps(c.get("result"), ensure_ascii=False) for c in record.get("tool_calls") or []]
    return "\n".join(parts).replace(",", "")


def unsupported_claims(answer: str, record: dict) -> List[str]:
    """Specific facts in the answer that no tool result (or the prompt) contains."""
    text = re.sub(r"(?<=\d),(?=\d{3})", "", answer or "")
    evidence = evidence_text(record).lower()
    claims: List[str] = []
    for rx in (CODE_RE, LOT_RE, BIG_NUM_RE):
        for m in rx.finditer(text):
            if m.group(0).lower() not in evidence:
                claims.append(m.group(0))
    for m in NAME_RE.finditer(text):  # the regex may swallow leading words ("Source Name X #1"): accept a >=3-word tail
        words = m.group(0).split()
        need = min(3, len(words))
        if not any(" ".join(words[i:]).lower() in evidence for i in range(len(words) - need + 1)):
            claims.append(m.group(0))
    for m in COUNT_RE.finditer(text):
        if not re.search(rf"(?<!\d){m.group(1)}(?!\d)", evidence):
            claims.append(m.group(0))
    seen, unique = set(), []
    for c in claims:
        if c.lower() not in seen:
            seen.add(c.lower())
            unique.append(c)
    return unique


def _calls(record: dict, tool: str) -> List[dict]:
    return [c for c in record.get("tool_calls") or [] if c.get("tool") == tool and c.get("ok")]


def _arg(call: dict, name: str) -> Any:
    return (call.get("arguments") or {}).get(name)


def required_lookups(task_id: str, record: dict, expected: dict) -> List[str]:
    missing: List[str] = []
    if task_id == "A":
        if not any("yogurt" in str(_arg(c, "query")).lower() for c in _calls(record, "search_recalls")):
            missing.append("no successful search_recalls for 'Farmstead Yogurt'")
        if not any(_arg(c, "record_id") == expected["id"] for c in _calls(record, "recall_detail")):
            missing.append(f"no recall_detail lookup of record {expected['id']}")
    elif task_id == "B":
        if not any(_arg(c, "source_id") == 611 for c in _calls(record, "source_recall_summary")):
            missing.append("no source_recall_summary lookup of source 611")
        if not any(_arg(c, "record_id") == 15013 for c in _calls(record, "recall_detail")):
            missing.append("no recall_detail lookup of record 15013")
    elif task_id == "C":
        for rid in expected["ids"]:
            if not any(_arg(c, "record_id") == rid for c in _calls(record, "recall_detail")):
                missing.append(f"no recall_detail lookup of record {rid}")
    return missing


def verify_task(task_id: str, record: dict, expected: dict) -> Dict[str, Any]:
    problems: List[Dict[str, str]] = []
    content_ok, content_problems = content_verify(task_id, record, expected)
    for p in content_problems:
        problems.append({"rule": "answer_content", "detail": p})
    missing = required_lookups(task_id, record, expected)
    for p in missing:
        problems.append({"rule": "required_lookup", "detail": p})
    answer = record.get("final_text") or ""
    unsupported = unsupported_claims(answer, record) if record.get("stop_reason") == "final_answer" else []
    for c in unsupported:
        problems.append({"rule": "unsupported_claim", "detail": f"'{c}' is not in any tool result"})
    return {"ok": not problems, "problems": problems, "content_ok": content_ok and not unsupported,
            "process_ok": not missing, "unsupported_claims": unsupported}
