"""HW10 Part 2.2: score one request (a bundle from collector.py) on the four criteria and write the result.

    plan_quality          the Planner's steps for the question                  1-5 + reason
    writer_helpfulness    the Writer's draft                                    1-5 + reason + trace_id
    final_helpfulness     the Reviewer's final answer                           1-5 + the final answer
    improvement           final score - draft score, with an interpretation

A judge failure never stops the run: that metric is stored as score=null with the error text, the others still run, and each
case has a time budget. One "evaluator" span per request (trace_id, start, end, status) goes to the tracing file."""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "code") not in sys.path:
    sys.path.insert(0, str(REPO / "code"))

from evaluation.collector import plan_text  # noqa: E402
from evaluation.rubrics import score_one  # noqa: E402
from tracing.spans import emit, now_ms  # noqa: E402

RAW = REPO / "reports" / "hw10" / "raw"
BUNDLES_PATH = Path(os.environ.get("HW10_BUNDLES_PATH", RAW / "bundles.jsonl"))
EVALS_PATH = Path(os.environ.get("HW10_EVALS_PATH", RAW / "evaluations.jsonl"))
CASE_BUDGET_S = float(os.environ.get("HW10_CASE_BUDGET", "900"))
RUBRIC_VERSION = "hw10-v1 (1-5, fixed evaluation steps)"


def interpret(draft_score: Optional[int], final_score: Optional[int], draft: Optional[str], final: Optional[str],
              status: Optional[str]) -> str:
    if draft_score is None or final_score is None:
        return "not computed: at least one judge score is missing (see the error fields)"
    diff = final_score - draft_score
    same_text = bool(draft) and draft == final
    base = ("the final answer scored higher than the draft" if diff > 0 else
            "the final answer scored lower than the draft" if diff < 0 else "no change between draft and final answer")
    if same_text:
        note = ("The Reviewer passed the draft through word for word (final == draft), so the pipeline did not change the "
                "answer; " + ("any non-zero difference here is judge noise, not Reviewer improvement."
                              if diff else "a difference of 0 is the expected result."))
    elif status == "rejected":
        note = "The Reviewer rejected the draft, so the final message is a rejection, not an improved answer."
    else:
        note = "The final text differs from the draft."
    return f"{base} ({diff:+d}). {note}"


def evaluate_bundle(bundle: Dict[str, Any], metrics: Dict[str, Any], judge_name: str = "",
                    budget_s: float = CASE_BUDGET_S) -> Dict[str, Any]:
    tid = bundle.get("trace_id")
    t0, start = time.monotonic(), now_ms()
    question = bundle.get("question")
    result: Dict[str, Any] = {
        "trace_id": tid, "question": question, "judge_model": judge_name, "rubric": RUBRIC_VERSION,
        "evaluated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "missing_parts": list(bundle.get("missing") or []), "scores": {}, "inputs": {
            "plan": plan_text(bundle.get("plan")), "draft": bundle.get("draft"), "final_answer": bundle.get("final_answer"),
            "final_status": bundle.get("final_status")},
    }
    work = (("plan_quality", plan_text(bundle.get("plan"))), ("writer_helpfulness", bundle.get("draft")),
            ("final_helpfulness", bundle.get("final_answer")))
    for key, output in work:
        t = time.monotonic()
        if not isinstance(question, str) or not question.strip() or not isinstance(output, str) or not output.strip():
            res = {"score": None, "raw": None, "reason": "", "error": "input missing: nothing to judge"}
        elif time.monotonic() - t0 > budget_s:
            res = {"score": None, "raw": None, "reason": "", "error": f"case time budget of {budget_s:.0f}s exceeded"}
        else:
            res = score_one(metrics[key], question, output)
        res["judge_ms"] = round((time.monotonic() - t) * 1000, 1)
        result["scores"][key] = res
    s = result["scores"]
    result["writer_helpfulness_trace_id"] = tid
    result["improvement"] = {
        "draft_score": s["writer_helpfulness"]["score"], "final_score": s["final_helpfulness"]["score"],
        "difference": (None if None in (s["writer_helpfulness"]["score"], s["final_helpfulness"]["score"])
                       else s["final_helpfulness"]["score"] - s["writer_helpfulness"]["score"]),
        "identical_text": bool(bundle.get("draft")) and bundle.get("draft") == bundle.get("final_answer"),
        "interpretation": interpret(s["writer_helpfulness"]["score"], s["final_helpfulness"]["score"],
                                    bundle.get("draft"), bundle.get("final_answer"), bundle.get("final_status")),
    }
    errors = [k for k, v in s.items() if v["error"]]
    result["status"] = "ok" if not errors else ("error" if len(errors) == len(s) else "partial")
    result["errors"] = {k: s[k]["error"] for k in errors}
    result["evaluation_ms"] = round((time.monotonic() - t0) * 1000, 1)
    emit(tid, "evaluator", start, now_ms(), "ok" if result["status"] == "ok" else "error",
         "; ".join(f"{k}: {v}" for k, v in result["errors"].items()) or None, judge_model=judge_name,
         scores={k: v["score"] for k, v in s.items()})
    return result


def append_results(results: Iterable[Dict[str, Any]], path: Path = EVALS_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for r in results:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def load_results(path: Path = EVALS_PATH) -> list:
    out: list = []
    if Path(path).exists():
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    return out
