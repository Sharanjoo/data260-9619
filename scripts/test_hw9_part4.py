"""HW9 Part 4 offline tests (no Ollama, no Kafka, no Redis): evaluator rules, lessons, retry loop, training, gate, variants.

    python scripts/test_hw9_part4.py

A scripted fake model stands in for qwen3:8b: it reports the ORIGINAL figures of a notice unless a lesson about UPDATEs is in
its prompt or a reviewer's feedback is attached, answers only the first part of a two-part question unless the
'answer both parts' lesson is present, and invents an answer when no notice matches unless the 'do not have that
information' lesson is present."""
from __future__ import annotations

import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "code"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import hw9_part4_train as train  # noqa: E402
import hw9_part4_validate as validate  # noqa: E402
import hw9_part4_variants as variants  # noqa: E402
from two_agents import textmatch as tm  # noqa: E402
from two_agents.evaluator import Evaluator  # noqa: E402
from two_agents.lessons import LessonStore  # noqa: E402
from two_agents.pipeline import build_system, load_data, read_jsonl, summarize  # noqa: E402
from two_agents.reference import detect_intents, find_notice  # noqa: E402

DATA = load_data()
REF = DATA["reference"]
PASSED = 0


def check(name: str, cond: bool) -> None:
    global PASSED
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        raise SystemExit(1)
    PASSED += 1


def fields(block: str) -> dict:
    g = lambda label: (re.search(rf"{label}: ([^.]*?)\.(?:\s|$)", block) or [None, ""])[1].strip()  # noqa: E731
    return {"units": g("Units affected"), "lots": g("Lot codes"), "states": g("Sold in"), "deadline": g("Refund deadline")}


class FakeModel:
    """Behaves like a small model that tends to read the first announcement and drop the second half of a question."""
    model = "fake-model"

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, system: str, user: str) -> str:
        self.calls += 1
        q = re.search(r"Question: (.*?)(?:\n\n|$)", user, re.S).group(1)
        notice = user.split("Recall notice:\n", 1)[1].split("\n\nQuestion:", 1)[0]
        if notice.startswith("No matching"):
            return ("I do not have that information." if ("do not have that information" in system or "reviewer found" in user)
                    else "It was recalled for 12,345 units, lot AB-1234, refund by 2026-12-01.")
        lines = notice.splitlines()
        use_update = len(lines) > 1 and ("most recent UPDATE" in system or "reviewer found" in user)
        block = lines[-1] if use_update else lines[0]
        f = fields(block)
        if "fined" in q.lower() or "ceo" in q.lower() or "cost" in q.lower():
            return ("I do not have that information." if ("do not have that information" in system or "reviewer found" in user)
                    else "It was fined $50,000.")
        intents = detect_intents(q)
        if len(intents) > 1 and "answer both parts" not in system and "Check each part" not in system \
                and "reviewer found" not in user:
            intents = intents[:1]
        parts = []
        for i in intents:
            if i == "units":
                parts.append(f"{f['units']} units are affected")
            elif i == "lots":
                parts.append(f"the lot codes are {f['lots']}")
            elif i == "states":
                parts.append(f"it was sold in {f['states']}")
            elif i == "deadline":
                parts.append(f"refunds are available until {f['deadline']}")
            elif i == "status":
                parts.append("the recall is expanded" if use_update else "the recall is active")
            elif i == "hazard":
                parts.append("it was recalled because of " + re.search(r"because of ([^.]*)\.", notice).group(1))
            elif i == "action":
                parts.append("do not eat it; return it to the store for a refund or throw it away")
        text = "; ".join(parts)
        return text[0].upper() + text[1:] + "."


def unit_tests() -> None:
    n1 = REF[0]  # updated notice
    n3 = REF[2]  # RN-003: i % 3 == 0 -> not updated
    ev = Evaluator(REF)
    check("data: 18 notices, 12 updated", len(REF) == 18 and sum(1 for n in REF if n["updated_on"]) == 12)
    check("data: 40/14/20 questions", (len(DATA["training"]), len(DATA["validation"]), len(DATA["test"])) == (40, 14, 20))
    for name in ("training", "validation", "test"):
        check(f"{name}_data.json holds only id and question",
              all(set(q) == {"id", "question"} for q in DATA[name]))
    names = lambda split: {find_notice(q["question"], REF)["notice_id"] for q in DATA[split] if find_notice(q["question"], REF)}  # noqa: E731
    check("splits use different notices", not (names("training") & names("validation") or names("training") & names("test")
                                               or names("validation") & names("test")))
    q = f"How many units of {n1['brand']} {n1['product']} are affected by the recall?"
    check("matchers: number with comma", tm.has_number("about 6,260 units", 6260) and not tm.has_number("16,2605", 6260))
    check("matchers: date forms", tm.has_date("until December 12, 2026", "2026-12-12") and tm.has_date("by Dec 12", "2026-12-12"))
    cur, old = n1["units_affected"]["current"], n1["units_affected"]["initial"]
    check("evaluator: current value passes", ev.evaluate(q, f"{cur:,} units are affected.")["passed"])
    r = ev.evaluate(q, f"{old:,} units are affected.")
    check("evaluator: original value is stale_value", (not r["passed"]) and r["pattern"] == "stale_value")
    check("evaluator: feedback does not leak the answer", f"{cur:,}" not in r["feedback"] and str(cur) not in r["feedback"])
    r = ev.evaluate(q, "Many units were affected.")
    check("evaluator: absent value is missing_value", r["pattern"] == "missing_value")
    r = ev.evaluate(q, "I do not have that information.")
    check("evaluator: refusing an answerable question fails", not r["passed"] and r["pattern"] == "missing_value")
    q2 = f"How many units of {n1['brand']} {n1['product']} are affected, and by what date can I get a refund?"
    r = ev.evaluate(q2, f"{cur:,} units are affected.")
    check("evaluator: half an answer is incomplete_multi", r["pattern"] == "incomplete_multi" and r["failed_intents"] == ["deadline"])
    full = f"{cur:,} units are affected; refunds until {n1['refund_deadline']['current']}."
    check("evaluator: both parts pass", ev.evaluate(q2, full)["passed"])
    q3 = f"Is the {n1['brand']} {n1['product']} recall still active, expanded or closed?"
    check("evaluator: status expanded", ev.evaluate(q3, "It has been expanded.")["passed"]
          and ev.evaluate(q3, "It is still active.")["pattern"] == "stale_value")
    q4 = f"Is the {n3['brand']} {n3['product']} recall still active, expanded or closed?"
    check("evaluator: unchanged notice, active is right", ev.evaluate(q4, "The recall is still active.")["passed"])
    check("evaluator: lots need every current lot", not ev.evaluate(
        f"Which lot codes does the {n1['brand']} {n1['product']} recall cover?", n1["lot_codes"]["initial"][0])["passed"])
    oq = f"Who is the CEO of {n1['brand']}?"
    check("evaluator: refusal expected for CEO question", ev.expected_scope(oq) == "refuse")
    check("evaluator: refusal passes", ev.evaluate(oq, "I do not have that information.")["passed"])
    check("evaluator: invented answer is fabricated_answer", ev.evaluate(oq, "The CEO is Pat Lee.")["pattern"] == "fabricated_answer")
    check("evaluator: refusal with invented number fails",
          ev.evaluate(oq, "I do not have that, but sales were 12,000 units.")["pattern"] == "fabricated_answer")
    for phrase in ("The recall notice does not provide information about the CEO of Harvest Valley.",
                   "The notice does not mention any fines or penalties.", "No such recall is listed."):
        check(f"evaluator: refusal wording accepted: {phrase[:40]}", ev.evaluate(oq, phrase)["passed"])
    na = REF[1]
    r = ev.evaluate(f"What should I do with {na['brand']} {na['product']} that I already bought?",
                    "Return the product to the store for a refund or throw it away.")
    check("evaluator: advice without the do-not-eat instruction fails", (not r["passed"]) and "eaten or used" in r["feedback"])
    check("evaluator: unknown product expects refusal", ev.expected_scope("Is there a recall on Organic Bananas from Sunny Groves?") == "refuse")


def lesson_tests(tmp: Path) -> None:
    s = LessonStore(tmp / "l.json")
    check("lessons: first occurrence creates nothing", s.record_failure("stale_value") is None and not s.lessons)
    new = s.record_failure("stale_value")
    check("lessons: second occurrence creates a lesson", new is not None and new["lesson_id"] == "L001" and new["use_count"] == 0)
    check("lessons: no duplicate for the same pattern", s.record_failure("stale_value") is None and len(s.lessons) == 1)
    check("lessons: required fields", set(new) == {"lesson_id", "failure_pattern", "correction", "created_at", "use_count"})
    s.save()
    again = LessonStore(tmp / "l.json")
    check("lessons: saved and reloaded", len(again.lessons) == 1 and again.occurrences["stale_value"] == 3)
    block = again.prompt_block()
    check("lessons: prompt block counts a use", "UPDATE" in block and again.lessons[0]["use_count"] == 1)
    check("lessons: only() copies", len(again.only(["L001"]).lessons) == 1 and not again.only([]).lessons)


def system_tests(tmp: Path) -> None:
    model = FakeModel()
    store = LessonStore(tmp / "none.json")
    sysm = build_system(model, DATA, store)
    qs = {q["id"]: q["question"] for q in DATA["training"]}
    r = sysm.run("T01", qs["T01"], retry=False)
    check("system: updated notice, no lessons, no retry -> fails with stale_value", not r["passed_final"] and r["first_pattern"] == "stale_value")
    r = sysm.run("T01", qs["T01"], retry=True)
    check("system: retry with feedback fixes it", (not r["passed_first"]) and r["passed_final"] and r["n_attempts"] == 2)
    r = sysm.run("T01", qs["T01"], retry=True, first_answer="Blah.")
    check("system: forced first answer is marked", r["attempts"][0]["forced"] and r["attempts"][0]["answer"] == "Blah.")
    r = sysm.run("T14", qs["T14"], retry=True)
    check("system: fabricated answer repaired by retry", r["first_pattern"] == "fabricated_answer" and r["passed_final"])
    r = sysm.run("T05", qs["T05"], retry=True)
    check("system: at most two attempts", r["n_attempts"] <= 2)
    store.lessons.append({"lesson_id": "L001", "failure_pattern": "stale_value",
                          "correction": "Always report values from the most recent UPDATE.", "created_at": "x", "use_count": 0})
    sysm2 = build_system(FakeModel(), DATA, store)
    r = sysm2.run("T01", qs["T01"], retry=False)
    check("system: a lesson lets the first attempt pass", r["passed_first"] and store.lessons[0]["use_count"] >= 1)


def flow_tests(tmp: Path) -> None:
    raw, cand, acc = tmp / "raw", tmp / "cand.json", tmp / "lessons.json"
    for mod in (train, validate, variants):
        mod.OllamaLLM = lambda: FakeModel()
        mod.RAW = raw
    train.CANDIDATES = validate.CANDIDATES = cand
    validate.ACCEPTED = variants.ACCEPTED = acc
    check("train: runs", _run(train))
    store = LessonStore(cand)
    patterns = {x["failure_pattern"] for x in store.lessons}
    check("train: lessons created for repeated patterns", "stale_value" in patterns and "fabricated_answer" in patterns)
    rows = read_jsonl(raw / "part4_train.jsonl")
    check("train: 40 results saved", len(rows) == 40)
    before = len(rows)
    _run(train)
    check("train: resume does not repeat questions", len(read_jsonl(raw / "part4_train.jsonl")) == before)
    check("validate: runs", _run(validate))
    gate = json.loads((raw / "part4_gate.json").read_text())
    check("validate: stale and fabricated lessons accepted", len(gate["accepted"]) >= 2)
    check("validate: C0 baseline below the lessons run", gate["C2"]["summary"]["first_pass"] > gate["C0"]["first_pass"])
    check("validate: no regressions in the combined run", gate["C2"]["broken"] == [])
    accepted = LessonStore(acc)
    check("validate: lessons.json written", len(accepted.lessons) == len(gate["accepted"]))
    check("variants: runs", _run(variants))
    table = json.loads((raw / "part4_variants.json").read_text())
    check("variants: V1 < V4 on the test set", table["V1"]["final_pass"] < table["V4"]["final_pass"])
    check("variants: V2 retry rescues failures", table["V2"]["rescued"] > 0 and table["V2"]["mean_attempts"] > 1)
    check("variants: V3 lessons raise first-attempt passes", table["V3"]["first_pass"] > table["V1"]["first_pass"])
    check("variants: V4 first pass >= V3 first pass", table["V4"]["first_pass"] >= table["V3"]["first_pass"])
    check("variants: V4 needs fewer retries than V2", table["V4"]["mean_attempts"] < table["V2"]["mean_attempts"])
    check("variants: use_count updated", sum(x["use_count"] for x in LessonStore(acc).lessons) > 0)
    check("summarize: empty", summarize([]) == {"n": 0})


def _run(mod) -> bool:
    argv, sys.argv = sys.argv, [mod.__name__]
    try:
        return mod.main() == 0
    finally:
        sys.argv = argv


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="hw9p4_"))
    try:
        unit_tests()
        lesson_tests(tmp)
        system_tests(tmp)
        flow_tests(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{PASSED}/{PASSED} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
