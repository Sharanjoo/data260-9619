"""HW10 Part 3.1: build the 20 Writer drafts that Jo labels by hand and the judge is later validated on.

    python scripts/hw10_make_cases.py questions     -> data/hw10/part3_questions.json   (no services needed)
    python scripts/hw10_make_cases.py run           -> sends the 20 questions through the pipeline, one after another
                                                       (docker compose up -d + Planner, Writer, Reviewer running + Ollama)
                                                       resumable: data/hw10/part3_runs.json remembers finished cases
    python scripts/hw10_make_cases.py collect       -> data/hw10/eval_cases.json + human_labels.csv (blank) + labeling_sheet.md

Questions: 10 about a recall record (facts from the database are added by the ingress, exactly as in HW9), 5 general shopper
questions, 5 hard ones (unknown record, no phone number available, cooking, pets, off topic). They are mixed and given
neutral ids C01..C20, so the id does not reveal the kind. Requests are sent with the cache OFF so Redis is not touched.
The labeling sheet shows the question and the draft only - never a judge score (none exists yet)."""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import random
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "code"))

from cache_layer.config import SEED  # noqa: E402

DATA = REPO / "data" / "hw10"
PICKED = REPO / "reports" / "hw09" / "raw" / "records_picked.json"
QUESTIONS = DATA / "part3_questions.json"
RUNS = DATA / "part3_runs.json"
CASES = DATA / "eval_cases.json"
LABELS = DATA / "human_labels.csv"
SHEET = DATA / "labeling_sheet.md"
BANNER = "Sharan Lourduraj | SID4 9619 | DATA 260 HW10 Part 3 (cases)"

RECORD_TEMPLATES = [
    ("region", "Which region does the agency that reported recall {code} ({product}, {brand}) belong to?"),
    ("units_and_action", "Recall {code} covers {product} from {brand}. How many units were affected, and what should I do if I have some?"),
    ("agency_and_units", "Who reported recall {code} for {product} and how many units are involved?"),
    ("brand", "Which brand made the product in recall {code} ({product})?"),
    ("product", "What product is recall {code} about, and who sells it?"),
    ("comparison", "Is recall {code} ({product} from {brand}) bigger than a typical grocery recall?"),
    ("owned", "I bought {product} made by {brand}. Is it covered by recall {code}?"),
    ("region_agency", "Which agency and which region reported recall {code} for {brand} {product}?"),
    ("date", "On what date was recall {code} ({product}, {brand}) announced?"),
    ("summary", "Summarize recall {code} ({product}, {brand}) for a shopper in two sentences."),
]
GENERAL = [
    ("general", "I am pregnant and I think I ate a recalled product yesterday. What should I do?"),
    ("general", "Can I return a recalled product to the store without the receipt?"),
    ("general", "How do I find out whether something in my kitchen has been recalled?"),
    ("general", "Is it enough to wash a recalled vegetable before eating it?"),
    ("general", "I already threw the recalled item away. Do I still need to do anything?"),
]
HARD = [
    ("unknown_record", "How many units were affected by recall REC-999999?"),
    ("needs_phone", "What phone number do I call to report that I got sick from a recalled product?"),
    ("cooking", "If I cook the recalled frozen berries thoroughly, is it safe to eat them?"),
    ("pet", "My dog ate some of a recalled snack. Should I be worried?"),
    ("off_topic", "What will the weather be like tomorrow in San Jose?"),
]


def build_questions() -> list:
    picked = json.loads(PICKED.read_text(encoding="utf-8"))["groups"]["base"]
    items = []
    for i, (kind, tpl) in enumerate(RECORD_TEMPLATES):
        rec = picked[i]
        items.append({"category": f"record:{kind}", "record_code": rec["record_code"],
                      "text": tpl.format(code=rec["record_code"], product=rec["product_name"], brand=rec["brand_name"])})
    for kind, text in GENERAL + HARD:
        items.append({"category": kind, "record_code": None, "text": text})
    random.Random(SEED).shuffle(items)
    for n, it in enumerate(items, 1):
        it["case_id"] = f"C{n:02d}"
    return items


def load(path: Path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def cmd_questions() -> int:
    DATA.mkdir(parents=True, exist_ok=True)
    items = build_questions()
    QUESTIONS.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")
    for it in items:
        print(f"{it['case_id']}  [{it['category']:22s}] {it['text']}")
    print(f"\nwrote {len(items)} questions to {QUESTIONS.relative_to(REPO)}")
    return 0


async def cmd_run() -> int:
    from cache_layer.agent_client import AgentClient
    from cache_layer.facts import FactsStore
    from cache_layer.ingress import SemanticIngress

    items = load(QUESTIONS, [])
    if not items:
        print("run `questions` first")
        return 1
    runs = load(RUNS, {})
    agent = AgentClient()
    await agent.start()
    try:
        ingress = SemanticIngress(None, None, FactsStore(), agent)
        for it in items:
            if it["case_id"] in runs and runs[it["case_id"]].get("status") == "approved":
                print(f"{it['case_id']} already done (trace_id {runs[it['case_id']]['trace_id']})")
                continue
            res = await ingress.answer(it["text"], use_cache=False, tag=it["case_id"])
            runs[it["case_id"]] = {"trace_id": res["trace_id"], "status": res["status"],
                                   "latency_ms": res["latency_ms"], "finished_at": res["finished_at"]}
            RUNS.write_text(json.dumps(runs, indent=2), encoding="utf-8")
            print(f"{it['case_id']} status={res['status']} latency={res['latency_ms'] / 1000:.0f}s trace_id={res['trace_id']}", flush=True)
    finally:
        await agent.stop()
    bad = [c for c, r in runs.items() if r["status"] != "approved"]
    print(f"{len(runs)}/{len(items)} requests finished; not approved: {bad or 'none'}")
    return 0 if len(runs) == len(items) and not bad else 1


async def cmd_collect() -> int:
    from evaluation.collector import collect_from_kafka

    items, runs = load(QUESTIONS, []), load(RUNS, {})
    ids = [runs[it["case_id"]]["trace_id"] for it in items if it["case_id"] in runs]
    got = await collect_from_kafka(ids, 60.0)
    cases = []
    for it in items:
        run = runs.get(it["case_id"])
        b = got["bundles"].get(run["trace_id"]) if run else None
        if not b or b["missing"]:
            print(f"{it['case_id']}: incomplete ({b['missing'] if b else 'not run'}) - skipped")
            continue
        cases.append({"case_id": it["case_id"], "category": it["category"], "trace_id": b["trace_id"],
                      "user_question": it["text"], "question_sent_to_pipeline": b["question"],
                      "plan": b["plan"], "draft": b["draft"], "final_status": b["final_status"],
                      "writer": b["messages"]["draft"].get("writer"), "writer_model": "qwen3:8b (Ollama, temperature 0)",
                      "kafka": b["kafka"]["draft"]})
    if len(cases) != len(items):
        print(f"only {len(cases)}/{len(items)} cases complete: nothing written")
        return 1
    CASES.write_text(json.dumps({"homework": 10, "part": "3.1", "sid4": "9619", "n": len(cases), "cases": cases},
                                indent=2, ensure_ascii=False), encoding="utf-8")
    if not LABELS.exists():
        with LABELS.open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["case_id", "human_label", "notes"])
            for c in cases:
                w.writerow([c["case_id"], "", ""])
    lines = ["# HW10 Part 3.1 - labeling sheet (Sharan Lourduraj, SID4 9619)", "",
             "Give each draft ONE whole number 1-5 for helpfulness in `human_labels.csv`. Rubric: LABELING_RUBRIC.md. "
             "Label from the question and the draft only.", ""]
    for c in cases:
        lines += [f"## {c['case_id']}", "", "**Question sent to the writer (facts included when the ingress added them):**", "",
                  "> " + c["question_sent_to_pipeline"].replace("\n", "\n> "), "", "**Draft:**", "",
                  "> " + c["draft"].replace("\n", "\n> "), "", "Label (1-5): ____", ""]
    SHEET.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {CASES.relative_to(REPO)} ({len(cases)} drafts), {LABELS.relative_to(REPO)} (blank) and {SHEET.relative_to(REPO)}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["questions", "run", "collect"])
    step = ap.parse_args().step
    print(BANNER + f" | {step}", flush=True)
    if step == "questions":
        return cmd_questions()
    return asyncio.run(cmd_run() if step == "run" else cmd_collect())


if __name__ == "__main__":
    sys.exit(main())
