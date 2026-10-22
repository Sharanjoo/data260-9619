"""One-off: add the verifier verdict to records in reports/hw07/raw/agent_tasks.jsonl that were saved before
demo_agent_hw07.py wrote its records after verification (the four live runs of 2026-10-22 07:26-07:36Z).

It re-runs the SAME verifier (agent_tasks_hw07.verify) on the SAVED final answers; nothing is re-asked of the
model. Records are marked "verifier_backfilled": true. Run: $env:MYSQL_PORT="43306"; python scripts\\backfill_verifier_hw07.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from agent_tasks_hw07 import REPO, STUDENT_BANNER, expected_for, verify  # noqa: E402

PATH = REPO / "reports/hw07/raw/agent_tasks.jsonl"


def main() -> int:
    print(STUDENT_BANNER)
    rows = [json.loads(line) for line in PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    changed = 0
    for r in rows:
        if "answer_correct" in r:
            continue
        r["expected"] = expected_for(r["case_id"])
        r["answer_correct"], r["verifier_problems"] = verify(r["case_id"], r, r["expected"])
        r["verifier_backfilled"] = True
        changed += 1
    PATH.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    print(f"{PATH.relative_to(REPO)}: {changed} of {len(rows)} records backfilled")
    for r in rows:
        print(f"  task {r['case_id']} {r['timestamp']} calls={r['total_tool_calls']} invalid={r['invalid_calls']} "
              f"reprompts={r['repair_reprompts']} stop={r['stop_reason']} answer_correct={r['answer_correct']} "
              f"{r['verifier_problems'] or ''}")
    return 0 if all(r["answer_correct"] for r in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
