"""HW6 Part 4: consolidate the 55-line MEMORY_original.md and check the result against the ground truth.

    python scripts/recorded_run_hw06.py -- python scripts/run_consolidation_hw06.py

Steps: copy reports/hw06/MEMORY_original.md to a working file, show that the trigger fires (more than 40
lines AND older than 24 h), run /compact, write reports/hw06/MEMORY_consolidated.md, then compare the result
with reports/hw06/consolidation_truth.yaml (written before the first run): duplicates merged, contradictions
resolved correctly, nothing silently deleted, fewer than 40 lines. Exit code 0 only if every check passes.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import file_memory as fm  # noqa: E402
from src.model_client import ModelClientError, OllamaModelClient  # noqa: E402

REPORT_DIR = ROOT / "reports/hw06"
RAW = REPORT_DIR / "raw"


def contains(lines: list[str], needle: str) -> int:
    return sum(1 for line in lines if needle.lower() in line.lower())


def evaluate(text: str, truth: dict, report: fm.ConsolidationReport) -> tuple[list[tuple[str, bool, str]], list[str]]:
    """Return (checks, contradictions resolved incorrectly)."""
    fact_lines, conflict_lines = fm.split_memory(text)
    checks: list[tuple[str, bool, str]] = []
    wrong: list[str] = []

    checks.append(("fewer than 40 file lines", len(text.splitlines()) < fm.RESULT_LINE_LIMIT, f"{len(text.splitlines())} lines"))
    for group in truth["duplicate_groups"]:
        n = contains(fact_lines, group["key"])
        checks.append((f"{group['id']} duplicates merged into one line ('{group['key']}')", n == 1, f"{group['original_count']} -> {n}"))
    for item in truth["contradictions"]:
        keeper_ok = contains(fact_lines, item["keeper"]) == 1
        loser_gone = contains(fact_lines, item["loser"]) == 0
        loser_logged = contains(conflict_lines, item["loser"]) >= 1
        ok = keeper_ok and loser_gone and loser_logged
        unresolved = any(line.startswith("- UNRESOLVED") and item["loser"].lower() in line.lower() for line in conflict_lines)
        detail = f"keeper in Facts: {keeper_ok}, loser out of Facts: {loser_gone}, loser logged in Resolved conflicts: {loser_logged}" + (
            " (left UNRESOLVED: both kept, flagged for review)" if unresolved else ""
        )
        checks.append((f"{item['id']} contradiction resolved correctly", ok, detail))
        if not ok:
            wrong.append(f"{item['id']}: {item['note']} -> {detail}")
    missing = [key for key in truth["unique_facts"] if contains(fact_lines, key) != 1]
    checks.append(("all 19 unique facts survive exactly once", not missing, "missing/duplicated: " + ", ".join(missing) if missing else "19/19"))
    # an '- UNRESOLVED (both kept in Facts)' entry only describes two facts that are still in Facts, so it is not a removed fact
    removed_and_logged = [line for line in conflict_lines if not line.startswith("- UNRESOLVED")]
    accounted = len(fm.parse_facts(fact_lines)) + report.merged + len(removed_and_logged)
    original_facts = report.before_facts
    checks.append(("no silent deletion (kept + merged + logged = original facts)", accounted == original_facts, f"{len(fm.parse_facts(fact_lines))} kept + {report.merged} merged + {len(removed_and_logged)} logged = {accounted} (original {original_facts})"))
    return checks, wrong


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", default="qwen3:8b")
    parser.add_argument("--base-url", default="http://localhost:11434")
    args = parser.parse_args()

    RAW.mkdir(parents=True, exist_ok=True)
    work_dir = RAW / "consolidation_work"
    work_dir.mkdir(exist_ok=True)
    original = REPORT_DIR / "MEMORY_original.md"
    work = work_dir / "MEMORY.md"
    shutil.copyfile(original, work)
    truth = yaml.safe_load((REPORT_DIR / "consolidation_truth.yaml").read_text(encoding="utf-8"))

    print("HW6 Part 4 consolidation test - Sharan Lourduraj (SID4 9619)")
    original_text = original.read_text(encoding="utf-8")
    print(f"Original: {len(original_text.splitlines())} file lines, {fm.count_memory_lines(original_text)} memory lines (non-empty, non-comment)")
    print("Trigger check: consolidation required? ->", fm.consolidation_reasons(original_text) or "no")

    client = OllamaModelClient(model=args.model, base_url=args.base_url, timeout_seconds=1800)
    session = fm.FileMemorySession(client, ROOT / "AGENT.md", work)
    now = datetime.now(timezone.utc)
    print(f"\nRunning /compact (model {args.model}; this takes a few minutes on CPU) ...\n")
    try:
        report = fm.consolidate_file(work, client, now)
    except ModelClientError as exc:
        print(f"ERROR: {exc}")
        return 2
    print(report.summary())

    result_text = work.read_text(encoding="utf-8")
    shutil.copyfile(work, REPORT_DIR / "MEMORY_consolidated.md")
    print(f"\n----- consolidated file ({len(result_text.splitlines())} lines) -----\n{result_text}")

    checks, wrong = evaluate(result_text, truth, report)
    print("----- checks against consolidation_truth.yaml -----")
    for name, ok, detail in checks:
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")
    print("\nContradictions NOT resolved correctly:", "none" if not wrong else "")
    for line in wrong:
        print("  -", line)
    c2 = next(c for c in truth["contradictions"] if c["id"] == "C2")
    print(f"\nTrap C2 ({c2['note']}):")
    print("  guard interventions:", report.guard_notes or "none (the model itself left the critical allergy alone)")

    summary = {
        "model": args.model,
        "run_at": fm.format_timestamp(now),
        "report": {k: v for k, v in report.__dict__.items() if k != "proposed"},
        "model_decisions": report.proposed,
        "checks": [{"check": n, "passed": ok, "detail": d} for n, ok, d in checks],
        "resolved_incorrectly": wrong,
    }
    (RAW / "consolidation_result.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    failed = [n for n, ok, _ in checks if not ok]
    print(f"\n{len(checks) - len(failed)}/{len(checks)} checks passed. Raw result: reports/hw06/raw/consolidation_result.json")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
