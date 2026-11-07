"""HW9 Part 4: the four variants on test_data.json (held out: never used for training or validation).

    python scripts/recorded_run_hw09.py -- python scripts/hw9_part4_variants.py

  V1  baseline          one attempt, no lessons
  V2  retry only        up to 2 attempts with the Evaluator's feedback, no lessons
  V3  lessons only      one attempt, the accepted lessons in the prompt
  V4  lessons + retry   both
Each variant is a separate pass over the 20 test questions (same model settings: temperature 0, seed 9619). Per-question
results -> reports/hw09/raw/part4_variant_V*.jsonl (resumable); table -> reports/hw09/raw/part4_variants.json."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "code"))

from two_agents.lessons import LessonStore  # noqa: E402
from two_agents.llm import OllamaLLM  # noqa: E402
from two_agents.pipeline import ACCEPTED, BANNER, RAW, build_system, load_data, run_set, show, summarize  # noqa: E402

VARIANTS = [("V1", "baseline (no lessons, no retry)", False, False), ("V2", "retry only", True, False),
            ("V3", "lessons only", False, True), ("V4", "lessons + retry", True, True)]


def main() -> int:
    data = load_data()
    store = LessonStore(ACCEPTED)
    llm = OllamaLLM()
    system = build_system(llm, data, store)
    print(BANNER)
    print(f"model {llm.model} | {len(data['test'])} test questions | accepted lessons: "
          f"{[(x['lesson_id'], x['failure_pattern']) for x in store.lessons] or 'none'}")
    table = {}
    for vid, name, retry, lessons in VARIANTS:
        print(f"--- {vid}: {name}", flush=True)
        results = run_set(system, data["test"], out=RAW / f"part4_variant_{vid}.jsonl", on_result=lambda r: print(show(r), flush=True),
                          retry=retry, use_lessons=lessons)
        table[vid] = dict(summarize(results), name=name,
                          failed_final=[r["id"] for r in results if not r["passed_final"]])
        print(f"{vid}: {json.dumps(table[vid])}", flush=True)
    store.save()
    (RAW / "part4_variants.json").write_text(json.dumps(table, indent=2), encoding="utf-8")
    print(f"{'variant':8}{'first-attempt':>15}{'final':>8}{'mean attempts':>15}{'s/question':>12}")
    for vid, name, _, _ in VARIANTS:
        t = table[vid]
        print(f"{vid:8}{t['first_pass']:>12}/{t['n']}{t['final_pass']:>5}/{t['n']}{t['mean_attempts']:>15}{t['mean_seconds']:>12}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
