"""HW9 Part 4 validation gate: decide which candidate lessons are allowed into lessons.json.

    python scripts/recorded_run_hw09.py -- python scripts/hw9_part4_validate.py

Uses validation_data.json (questions only; different notices from training). All runs are FIRST attempt only, no retry:
  C0  no lessons                      (baseline)
  C1  one candidate lesson at a time  (each lesson alone)
  C2  all lessons that passed C1 together
Gate rule (--rule):
  strict  accept a lesson only if it fixes at least one question C0 got wrong and breaks none C0 got right (first version)
  net     accept a lesson if it fixes more questions than it breaks (net gain >= 1); breaks are still listed (default)
The combined C2 set must satisfy the same rule against C0; if it does not, the most recent lesson is dropped and C2 is repeated.
Accepted lessons -> data/hw09/lessons.json. With --rule strict the gate summary goes to part4_gate_strict.json.
Resumable: every run is cached in reports/hw09/raw/part4_validate_runs.jsonl."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "code"))

from two_agents.lessons import LessonStore  # noqa: E402
from two_agents.llm import OllamaLLM  # noqa: E402
from two_agents.pipeline import ACCEPTED, BANNER, CANDIDATES, RAW, build_system, load_data, run_set, summarize  # noqa: E402


def passed_ids(results: list) -> set:
    return {r["id"] for r in results if r["passed_first"]}


def decide(rule: str, fixed: list, broken: list) -> str:
    """accept / reject / inconclusive for a lesson (or a lesson set) compared with the no-lesson baseline."""
    if rule == "strict":
        return "accept" if fixed and not broken else ("reject" if broken else "inconclusive")
    net = len(fixed) - len(broken)
    return "accept" if net >= 1 else ("reject" if net < 0 else "inconclusive")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rule", choices=["strict", "net"], default="net")
    args = ap.parse_args()
    data = load_data()
    candidates = LessonStore(CANDIDATES)
    llm = OllamaLLM()
    print(BANNER)
    print(f"model {llm.model} | {len(data['validation'])} validation questions | {len(candidates.lessons)} candidate lessons")
    if not candidates.lessons:
        print("no candidate lessons: run hw9_part4_train.py first")
        return 1

    def run(tag: str, ids: list) -> list:
        store = candidates.only(ids)
        system = build_system(llm, data, store)
        results = run_set(system, [dict(q, id=q["id"]) for q in data["validation"]], out=RAW / f"part4_validate_{tag}.jsonl",
                          retry=False, use_lessons=bool(ids))
        print(f"{tag}: lessons {ids or 'none'} -> first-attempt pass {len(passed_ids(results))}/{len(results)}", flush=True)
        return results

    c0 = run("C0", [])
    base = passed_ids(c0)
    report = {"rule": args.rule, "C0": summarize(c0), "C1": {}, "C2": {}, "accepted": []}
    keep = []
    for lesson in candidates.lessons:
        res = run(f"C1_{lesson['lesson_id']}", [lesson["lesson_id"]])
        now = passed_ids(res)
        fixed, broken = sorted(now - base), sorted(base - now)
        verdict = decide(args.rule, fixed, broken)
        report["C1"][lesson["lesson_id"]] = {"pattern": lesson["failure_pattern"], "pass": len(now), "fixed": fixed,
                                             "broken": broken, "verdict": verdict}
        print(f"  {lesson['lesson_id']} {lesson['failure_pattern']}: fixed {fixed} broken {broken} -> {verdict}")
        if verdict == "accept":
            keep.append(lesson["lesson_id"])
    while keep:
        res = run("C2_" + "_".join(keep), keep)
        now = passed_ids(res)
        fixed, broken = sorted(now - base), sorted(base - now)
        report["C2"] = {"lessons": list(keep), "summary": summarize(res), "fixed": fixed, "broken": broken}
        if decide(args.rule, fixed, broken) == "accept":
            break
        dropped = keep.pop()
        print(f"  combined set: fixed {fixed} broken {broken} fails the {args.rule} rule: dropping {dropped}")
        report.setdefault("dropped_in_C2", []).append(dropped)
    accepted = candidates.only(keep)
    accepted.path = ACCEPTED
    for x in accepted.lessons:
        x["use_count"] = 0
    accepted.occurrences = dict(candidates.occurrences)
    accepted.save()
    report["accepted"] = keep
    (RAW / ("part4_gate_strict.json" if args.rule == "strict" else "part4_gate.json")).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"accepted lessons: {keep or 'none'} -> {ACCEPTED}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
