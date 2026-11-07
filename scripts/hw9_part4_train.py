"""HW9 Part 4 training: run the two-agent system on training_data.json (questions only) and let it learn.

    python scripts/recorded_run_hw09.py -- python scripts/hw9_part4_train.py

For every training question the Answering Agent answers, the Evaluator checks the answer against the reference dataset, and
on a failure the agent retries once with the Evaluator's feedback. Each FIRST-attempt failure is counted by failure pattern;
when the same pattern has been seen twice, a lesson is created and goes into the prompt for the remaining questions.
Candidate lessons -> data/hw09/lessons_candidates.json (they are not trusted until hw9_part4_validate.py accepts them).
Resumable: results are appended to reports/hw09/raw/part4_train.jsonl. Needs Ollama (qwen3:8b); no Kafka or Redis."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "code"))

from two_agents.lessons import LessonStore  # noqa: E402
from two_agents.llm import OllamaLLM  # noqa: E402
from two_agents.pipeline import BANNER, CANDIDATES, RAW, build_system, load_data, run_set, show, summarize  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fresh", action="store_true", help="forget earlier training results and lessons")
    args = ap.parse_args()
    out = RAW / "part4_train.jsonl"
    if args.fresh:
        for p in (out, CANDIDATES):
            p.unlink(missing_ok=True)
    data = load_data()
    store = LessonStore(CANDIDATES)
    llm = OllamaLLM()
    system = build_system(llm, data, store)
    print(BANNER)
    print(f"model {llm.model} | {len(data['training'])} training questions | lessons so far: {len(store.lessons)}")

    def on_result(r: dict) -> None:
        if r["first_pattern"]:
            new = store.record_failure(r["first_pattern"])
            print(f"  failure pattern '{r['first_pattern']}' seen {store.occurrences[r['first_pattern']]} time(s)")
            if new:
                print(f"  -> NEW LESSON {new['lesson_id']} for '{new['failure_pattern']}'")
        store.save()
        print(show(r), flush=True)

    results = run_set(system, data["training"], out=out, on_result=on_result)
    store.save()
    print(json.dumps(summarize(results), indent=2))
    print(f"lessons created: {[(x['lesson_id'], x['failure_pattern']) for x in store.lessons]}")
    print(f"occurrences: {store.occurrences}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
