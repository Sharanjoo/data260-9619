"""HW10 Part 3.2 / 3.3: validate the judge against the human labels.

    python scripts/hw10_judge_validate.py run --run 1        judge the 20 Writer drafts once (run 1, 2 or 3); resumable
    python scripts/hw10_judge_validate.py run --run 2
    python scripts/hw10_judge_validate.py run --run 3
    python scripts/hw10_judge_validate.py stats              Spearman, mean absolute difference, repeatability -> reports/hw10/raw/

Order of work is enforced, not just promised: `run` refuses to start unless data/hw10/eval_cases.json and data/hw10/human_labels.csv
are complete (20 whole-number labels 1-5) AND committed in git with no later edit. The commit hash and time of those files are
written next to every judge score, so the report can show the labels existed before the first score.

Pre-declared analysis: 3.2 (agreement with the human labels) uses judge run 1; 3.3 (repeatability) uses runs 1, 2 and 3.
Judge settings, identical in every run: model qwen3:8b through Ollama, temperature 0, thinking off, fixed evaluation steps and
1-5 rubric (code/evaluation/rubrics.py), input = the question as the Writer received it, output = the draft. The judge reply
is a score 1-5 and a reason. Raw per-case rows go to reports/hw10/raw/judge_runs.csv so every statistic can be recomputed."""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "code"))

DATA = REPO / "data" / "hw10"
CASES = DATA / "eval_cases.json"
LABELS = DATA / "human_labels.csv"
RAW = REPO / "reports" / "hw10" / "raw"
RUNS_CSV = RAW / "judge_runs.csv"
BANNER = "Sharan Lourduraj | SID4 9619 | DATA 260 HW10 Part 3 (judge validation)"
COLUMNS = ["run", "case_id", "judge_score", "raw_geval", "reason", "error", "judge_ms", "judge_model", "temperature",
           "labels_commit", "labels_commit_time", "scored_at"]


# ---------- statistics (plain Python, so they can be recomputed anywhere) ----------
def ranks(values: List[float]) -> List[float]:
    """Average ranks (ties share the mean of their positions), 1-based."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    out = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            out[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return out


def pearson(x: List[float], y: List[float]) -> Optional[float]:
    n = len(x)
    mx, my = sum(x) / n, sum(y) / n
    sxx = sum((a - mx) ** 2 for a in x)
    syy = sum((b - my) ** 2 for b in y)
    if sxx == 0 or syy == 0:
        return None
    return sum((a - mx) * (b - my) for a, b in zip(x, y)) / (sxx * syy) ** 0.5


def spearman(x: List[float], y: List[float]) -> Optional[float]:
    """Spearman rank correlation = Pearson correlation of the average ranks (None if one side is constant)."""
    return pearson(ranks(x), ranks(y))


def agreement(human: Dict[str, int], judge: Dict[str, int]) -> dict:
    ids = sorted(set(human) & set(judge))
    h, j = [human[c] for c in ids], [judge[c] for c in ids]
    diffs = [b - a for a, b in zip(h, j)]
    return {"n": len(ids), "spearman": spearman(h, j), "mean_abs_diff": sum(abs(d) for d in diffs) / len(ids),
            "mean_signed_diff_judge_minus_human": sum(diffs) / len(ids), "within_1": sum(abs(d) <= 1 for d in diffs) / len(ids),
            "exact_match": sum(d == 0 for d in diffs) / len(ids), "max_abs_diff": max(abs(d) for d in diffs),
            "human_distribution": {str(k): h.count(k) for k in range(1, 6)},
            "judge_distribution": {str(k): j.count(k) for k in range(1, 6)}}


def repeatability(runs: Dict[int, Dict[str, int]]) -> dict:
    """runs: run number -> {case_id: score}. A case 'changed' if its scores differ across the runs."""
    ids = sorted(set.intersection(*(set(r) for r in runs.values())))
    nums = sorted(runs)
    per_case = {c: [runs[n][c] for n in nums] for c in ids}
    changed = [c for c, s in per_case.items() if len(set(s)) > 1]
    pair_changes = []
    for a in range(len(nums)):
        for b in range(a + 1, len(nums)):
            pair_changes += [abs(runs[nums[a]][c] - runs[nums[b]][c]) for c in ids]
    ranges = [max(s) - min(s) for s in per_case.values()]
    return {"runs": nums, "n_cases": len(ids), "cases_changed": len(changed), "fraction_changed": len(changed) / len(ids),
            "changed_case_ids": changed, "mean_abs_change_between_runs": sum(pair_changes) / len(pair_changes),
            "max_abs_change_between_runs": max(pair_changes), "mean_range_per_case": sum(ranges) / len(ranges),
            "max_range_per_case": max(ranges),
            "pair_fraction_unchanged": sum(1 for d in pair_changes if d == 0) / len(pair_changes)}


# ---------- inputs ----------
def load_labels(path: Path = LABELS) -> Dict[str, int]:
    """Labels from the CSV; raises ValueError unless every row is a whole number 1-5."""
    out: Dict[str, int] = {}
    with path.open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            cid = (row.get("case_id") or "").strip()
            if not cid:
                continue
            raw = (row.get("human_label") or "").strip()
            if not raw.isdigit() or not 1 <= int(raw) <= 5:
                raise ValueError(f"{cid}: human_label must be a whole number 1-5, found {raw!r}")
            out[cid] = int(raw)
    return out


def load_cases(path: Path = CASES) -> List[dict]:
    return json.loads(path.read_text(encoding="utf-8"))["cases"]


def git(*args: str, cwd: Path = REPO) -> Tuple[int, str]:
    p = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    return p.returncode, (p.stdout or "").strip()


def freeze_check(files: List[Path], cwd: Path = REPO) -> Tuple[bool, str, dict]:
    """The inputs must be committed and unmodified. Returns (ok, message, {commit, commit_time})."""
    info: dict = {}
    for f in files:
        rel = str(f.relative_to(cwd))
        rc, _ = git("ls-files", "--error-unmatch", rel, cwd=cwd)
        if rc != 0:
            return False, f"{rel} is not committed yet: commit eval_cases.json and human_labels.csv before running the judge", info
        _, status = git("status", "--porcelain", "--", rel, cwd=cwd)
        if status:
            return False, f"{rel} has changes that are not committed ({status}); labels may not change after commit", info
    _, line = git("log", "-1", "--format=%H|%cI", "--", *[str(f.relative_to(cwd)) for f in files], cwd=cwd)
    commit, _, when = line.partition("|")
    info = {"commit": commit, "commit_time": when}
    return True, f"inputs committed at {commit[:10]} ({when})", info


# ---------- runs ----------
def read_runs(path: Path = RUNS_CSV) -> List[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def append_row(row: dict, path: Path = RUNS_CSV) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists() or path.stat().st_size == 0
    with path.open("a", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        if new:
            w.writeheader()
        w.writerow(row)


def do_run(run: int, judge_model: str, metric_factory=None, cases: Optional[List[dict]] = None, info: Optional[dict] = None,
           runs_csv: Path = RUNS_CSV) -> List[dict]:
    from evaluation.judge import OllamaJudge
    from evaluation.rubrics import build_metrics, score_one

    cases = cases if cases is not None else load_cases()
    judge = OllamaJudge(model=judge_model) if metric_factory is None else metric_factory()
    metric = build_metrics(judge)["writer_helpfulness"]
    done = {r["case_id"] for r in read_runs(runs_csv) if r["run"] == str(run) and r["judge_score"] != ""}
    rows = []
    for i, c in enumerate(cases, 1):
        if c["case_id"] in done:
            continue
        t = time.perf_counter()
        res = score_one(metric, c["question_sent_to_pipeline"], c["draft"])
        row = {"run": run, "case_id": c["case_id"], "judge_score": "" if res["score"] is None else res["score"],
               "raw_geval": "" if res["raw"] is None else res["raw"], "reason": res["reason"].replace("\n", " "),
               "error": res["error"] or "", "judge_ms": round((time.perf_counter() - t) * 1000, 1),
               "judge_model": judge_model, "temperature": 0, "labels_commit": (info or {}).get("commit", ""),
               "labels_commit_time": (info or {}).get("commit_time", ""),
               "scored_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        append_row(row, runs_csv)
        rows.append(row)
        print(f"run {run} [{i:02d}/{len(cases)}] {c['case_id']} score={row['judge_score'] or 'ERROR'} "
              f"{row['judge_ms'] / 1000:.0f}s {row['error']}", flush=True)
    return rows


def scores_by_run(runs_csv: Path = RUNS_CSV) -> Dict[int, Dict[str, int]]:
    out: Dict[int, Dict[str, int]] = {}
    for r in read_runs(runs_csv):
        if r["judge_score"] != "":
            out.setdefault(int(r["run"]), {})[r["case_id"]] = int(r["judge_score"])
    return out


def do_stats(human: Dict[str, int], by_run: Dict[int, Dict[str, int]]) -> dict:
    result: dict = {"n_cases": len(human), "primary_run_for_3_2": 1}
    if 1 in by_run:
        result["agreement_run1"] = agreement(human, by_run[1])
    full = {n: s for n, s in by_run.items() if len(s) == len(human)}
    if len(full) >= 2:
        result["repeatability"] = repeatability(full)
        mean_scores = {c: sum(full[n][c] for n in full) / len(full) for c in human}
        h = [human[c] for c in sorted(human)]
        result["spearman_mean_of_runs_vs_human"] = spearman(h, [mean_scores[c] for c in sorted(human)])
        result["agreement_each_run"] = {str(n): agreement(human, full[n]) for n in sorted(full)}
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--run", type=int, choices=[1, 2, 3], required=True)
    r.add_argument("--judge-model", default="qwen3:8b")
    sub.add_parser("stats")
    args = ap.parse_args()
    print(BANNER + f" | {args.cmd}", flush=True)
    try:
        human = load_labels()
        cases = load_cases()
    except (OSError, ValueError, KeyError) as exc:
        print(f"cannot start: {exc}")
        return 1
    if sorted(human) != sorted(c["case_id"] for c in cases) or len(human) != 20:
        print(f"cannot start: the labels must cover exactly the 20 cases (have {len(human)} labels, {len(cases)} cases)")
        return 1
    if args.cmd == "run":
        ok, msg, info = freeze_check([CASES, LABELS])
        print(msg)
        if not ok:
            return 1
        do_run(args.run, args.judge_model, cases=cases, info=info)
        rows = [x for x in read_runs() if x["run"] == str(args.run)]
        errors = [x for x in rows if x["judge_score"] == ""]
        print(f"run {args.run}: {len(rows) - len(errors)}/{len(cases)} scored, {len(errors)} errors")
        return 0 if len(rows) == len(cases) and not errors else 1
    result = do_stats(human, scores_by_run())
    RAW.mkdir(parents=True, exist_ok=True)
    (RAW / "judge_validation.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    by_run = scores_by_run()
    with (RAW / "judge_validation_per_case.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["case_id", "human_label"] + [f"judge_run{n}" for n in sorted(by_run)] + ["judge_minus_human_run1"])
        for c in sorted(human):
            w.writerow([c, human[c]] + [by_run[n].get(c, "") for n in sorted(by_run)] +
                       [(by_run[1][c] - human[c]) if 1 in by_run and c in by_run[1] else ""])
    a = result.get("agreement_run1")
    if a:
        print(f"3.2 agreement (judge run 1 vs human, n={a['n']}): Spearman={a['spearman']}  mean abs diff={a['mean_abs_diff']:.2f}  "
              f"bias(judge-human)={a['mean_signed_diff_judge_minus_human']:+.2f}  within 1 point={a['within_1']:.0%}  exact={a['exact_match']:.0%}")
        print(f"    human distribution {a['human_distribution']}   judge distribution {a['judge_distribution']}")
    rep = result.get("repeatability")
    if rep:
        print(f"3.3 repeatability over runs {rep['runs']}: cases with any change {rep['cases_changed']}/{rep['n_cases']} "
              f"({rep['fraction_changed']:.0%}); mean abs change between runs {rep['mean_abs_change_between_runs']:.2f}; "
              f"max {rep['max_abs_change_between_runs']}")
    print(f"wrote {(RAW / 'judge_validation.json').relative_to(REPO)} and judge_validation_per_case.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
