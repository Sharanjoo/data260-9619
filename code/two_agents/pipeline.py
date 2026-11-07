"""HW9 Part 4: shared helpers for the training, validation, variants and demo scripts."""
from __future__ import annotations

import json
from pathlib import Path

from .answerer import AnsweringAgent
from .evaluator import Evaluator
from .lessons import LessonStore
from .llm import LLM
from .reference import load_json
from .system import TwoAgentSystem

ROOT = Path(__file__).resolve().parent.parent.parent
DATA = ROOT / "data" / "hw09"
RAW = ROOT / "reports" / "hw09" / "raw"
BANNER = "Sharan Lourduraj | SID4 9619 | DATA 260 HW9"
CANDIDATES = DATA / "lessons_candidates.json"   # written by training: every lesson created
ACCEPTED = DATA / "lessons.json"                # written by the validation gate: the lessons that passed it


def load_data(data_dir: Path = DATA) -> dict:
    return {"reference": load_json(data_dir / "reference_dataset.json")["notices"],
            "board": load_json(data_dir / "notice_board.json")["notices"],
            "training": json.loads((data_dir / "training_data.json").read_text(encoding="utf-8")),
            "validation": json.loads((data_dir / "validation_data.json").read_text(encoding="utf-8")),
            "test": json.loads((data_dir / "test_data.json").read_text(encoding="utf-8"))}


def build_system(llm: LLM, data: dict, store: LessonStore | None) -> TwoAgentSystem:
    return TwoAgentSystem(AnsweringAgent(llm, data["board"], store), Evaluator(data["reference"]))


def read_jsonl(path: Path) -> list:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def run_set(system: TwoAgentSystem, questions: list, out: Path | None = None, on_result=None, **kwargs) -> list:
    """Run every question; with `out`, results are appended as JSON lines and questions already there are skipped (resume)."""
    done = {r["id"]: r for r in read_jsonl(out)} if out else {}
    results = []
    for q in questions:
        if q["id"] in done:
            results.append(done[q["id"]])
            continue
        r = system.run(q["id"], q["question"], **kwargs)
        if out:
            append_jsonl(out, r)
        if on_result:
            on_result(r)
        results.append(r)
    return results


def summarize(results: list) -> dict:
    n = len(results)
    if not n:
        return {"n": 0}
    secs = sum(a["seconds"] for r in results for a in r["attempts"])
    return {"n": n, "first_pass": sum(r["passed_first"] for r in results),
            "final_pass": sum(r["passed_final"] for r in results),
            "first_pass_rate": round(sum(r["passed_first"] for r in results) / n, 3),
            "final_pass_rate": round(sum(r["passed_final"] for r in results) / n, 3),
            "mean_attempts": round(sum(r["n_attempts"] for r in results) / n, 2),
            "mean_seconds": round(secs / n, 1),
            "retried": sum(r["n_attempts"] > 1 for r in results),
            "rescued": sum((not r["passed_first"]) and r["passed_final"] for r in results)}


def show(r: dict) -> str:
    first = r["attempts"][0]
    mark = "PASS" if r["passed_first"] else f"FAIL({r['first_pattern']})"
    line = f"{r['id']} first={mark}"
    if r["n_attempts"] > 1:
        line += f" -> retry {'PASS' if r['passed_final'] else 'FAIL'}"
    return f"{line} | {r['question'][:70]} | {first['seconds']}s"
