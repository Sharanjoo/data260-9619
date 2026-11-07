"""HW9 Part 4 demo: one controlled bad-first-answer case, one normal answer, one out-of-scope question.

    python scripts/recorded_run_hw09.py -- python scripts/hw9_part4_demo.py

1. Controlled failure: the FIRST attempt is forced to be the original (pre-update) unit count of an updated notice, so the
   Evaluator must catch a stale_value failure and the second attempt must fix it using the Evaluator's feedback.
   The same forced answer is run without retry to show what the user would have received.
2. A normal question through the full system (accepted lessons + retry).
3. A question no notice can answer (CEO); the system must say it does not know.
Output: reports/hw09/raw/part4_demo.json."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "code"))

from two_agents.lessons import LessonStore  # noqa: E402
from two_agents.llm import OllamaLLM  # noqa: E402
from two_agents.pipeline import ACCEPTED, BANNER, RAW, build_system, load_data  # noqa: E402
from two_agents.reference import find_notice  # noqa: E402


def trace(r: dict) -> None:
    print(f"Q: {r['question']}")
    for a in r["attempts"]:
        tag = " (forced)" if a["forced"] else ""
        print(f"  attempt {a['attempt']}{tag}: {'PASS' if a['passed'] else 'FAIL ' + str(a['pattern'])}  [{a['seconds']}s]")
        print(f"    answer: {a['answer']}")
        if a["feedback"]:
            print(f"    evaluator feedback: {a['feedback']}")
    print(f"  final: {'PASS' if r['passed_final'] else 'FAIL'} after {r['n_attempts']} attempt(s)\n", flush=True)


def main() -> int:
    data = load_data()
    store = LessonStore(ACCEPTED)
    llm = OllamaLLM()
    system = build_system(llm, data, store)
    print(BANNER)
    print(f"model {llm.model} | accepted lessons: {[(x['lesson_id'], x['failure_pattern']) for x in store.lessons] or 'none'}\n")
    q = data["training"][0]["question"]  # How many units of <updated notice> ... (RN-001, updated after publication)
    n = find_notice(q, data["reference"])
    bad = (f"{n['brand']} {n['product']}: {n['units_affected']['initial']:,} units are affected by the recall "
           f"(published {n['published']}).")
    print("=== 1. Controlled bad first answer (original, pre-update unit count)")
    print(f"current value in the reference dataset: {n['units_affected']['current']:,}; original: {n['units_affected']['initial']:,}\n")
    print("-- without the retry loop (what the user would have received)")
    no_retry = system.run("DEMO1a", q, retry=False, first_answer=bad)
    trace(no_retry)
    print("-- with the retry loop")
    with_retry = system.run("DEMO1b", q, retry=True, first_answer=bad)
    trace(with_retry)
    print("=== 2. Normal question, full system")
    normal = system.run("DEMO2", data["validation"][0]["question"], retry=True)
    trace(normal)
    print("=== 3. Question outside the notices")
    outside = system.run("DEMO3", "Who is the CEO of Casa Dorada?", retry=True)
    trace(outside)
    store.save()
    (RAW / "part4_demo.json").write_text(json.dumps({"no_retry": no_retry, "with_retry": with_retry, "normal": normal,
                                                      "outside": outside}, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
