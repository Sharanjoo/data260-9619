"""HW10 Part 3 offline checks (python scripts/test_hw10_judge_validate.py): the statistics, the label checks, the freeze guard
(labels must be committed before the judge runs) and a scripted judge run. No Ollama, no real data."""
from __future__ import annotations

import csv
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hw10_judge_validate as v  # noqa: E402

passed = failed = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global passed, failed
    passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))


# ranks with ties and Spearman against known values
check("ranks: ties share the average rank", v.ranks([10, 20, 20, 30]) == [1.0, 2.5, 2.5, 4.0])
check("spearman: identical order is 1, reversed is -1", v.spearman([1, 2, 3, 4], [10, 20, 30, 40]) == 1.0
      and v.spearman([1, 2, 3, 4], [4, 3, 2, 1]) == -1.0)
check("spearman: a constant side has no correlation (None)", v.spearman([1, 2, 3], [3, 3, 3]) is None)
x, y = [1, 2, 3, 4, 5, 3, 4, 2], [2, 2, 4, 5, 5, 3, 3, 1]
sp = v.spearman(x, y)
try:
    from scipy.stats import spearmanr
    ref = float(spearmanr(x, y).statistic)
    check("spearman: matches scipy on data with ties", abs(sp - ref) < 1e-12, f"{sp:.6f} vs {ref:.6f}")
except ImportError:
    check("spearman: value on data with ties (scipy not installed)", abs(sp - 0.851852) < 1e-5, f"{sp:.4f}")

hum = {f"C{i:02d}": s for i, s in enumerate([1, 2, 3, 4, 5, 3], 1)}
jud = {f"C{i:02d}": s for i, s in enumerate([2, 2, 5, 4, 3, 3], 1)}
a = v.agreement(hum, jud)
check("agreement: MAD, bias, within-1, exact", abs(a["mean_abs_diff"] - 5 / 6) < 1e-12 and abs(a["mean_signed_diff_judge_minus_human"] - 1 / 6) < 1e-12
      and abs(a["within_1"] - 4 / 6) < 1e-12 and abs(a["exact_match"] - 3 / 6) < 1e-12 and a["max_abs_diff"] == 2, str(a))
runs = {1: {"A": 3, "B": 4, "C": 2}, 2: {"A": 3, "B": 5, "C": 2}, 3: {"A": 4, "B": 5, "C": 2}}
rp = v.repeatability(runs)
check("repeatability: 2 of 3 cases changed", rp["cases_changed"] == 2 and abs(rp["fraction_changed"] - 2 / 3) < 1e-12 and rp["changed_case_ids"] == ["A", "B"])
# pairs: (1,2): A0 B1 C0; (1,3): A1 B1 C0; (2,3): A1 B0 C0 -> sum 4 over 9
check("repeatability: mean and max absolute change over run pairs", abs(rp["mean_abs_change_between_runs"] - 4 / 9) < 1e-12 and rp["max_abs_change_between_runs"] == 1)
check("repeatability: identical runs give zero change", v.repeatability({1: {"A": 3}, 2: {"A": 3}})["fraction_changed"] == 0.0)

tmp = Path(tempfile.mkdtemp(prefix="hw10_val_"))
good = tmp / "good.csv"
good.write_text("case_id,human_label,notes\r\nC01,3,\r\nC02,5,ok\r\n", encoding="utf-8-sig")
check("labels: parses a CSV saved with a BOM and Windows line endings", v.load_labels(good) == {"C01": 3, "C02": 5})
for bad_text, why in (("case_id,human_label,notes\nC01,,\n", "blank"), ("case_id,human_label,notes\nC01,6,\n", "out of range"),
                      ("case_id,human_label,notes\nC01,3.5,\n", "not whole")):
    p = tmp / "bad.csv"
    p.write_text(bad_text)
    try:
        v.load_labels(p)
        check(f"labels: {why} is rejected", False)
    except ValueError:
        check(f"labels: {why} is rejected", True)

# freeze guard in a throw-away git repo
repo = tmp / "repo"
(repo / "data").mkdir(parents=True)
subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
for k, val in (("user.email", "t@t"), ("user.name", "t")):
    subprocess.run(["git", "config", k, val], cwd=repo, check=True)
cases_f, labels_f = repo / "data" / "eval_cases.json", repo / "data" / "human_labels.csv"
cases_f.write_text("{}")
labels_f.write_text("case_id,human_label,notes\n")
ok, msg, _ = v.freeze_check([cases_f, labels_f], cwd=repo)
check("freeze guard: refuses while the files are not committed", not ok and "not committed" in msg, msg)
subprocess.run(["git", "add", "data"], cwd=repo, check=True)
subprocess.run(["git", "commit", "-q", "-m", "x"], cwd=repo, check=True)
ok, msg, info = v.freeze_check([cases_f, labels_f], cwd=repo)
check("freeze guard: passes once committed, and returns the commit hash and time", ok and len(info["commit"]) == 40 and info["commit_time"], msg)
labels_f.write_text("case_id,human_label,notes\nC01,4,\n")
ok, msg, _ = v.freeze_check([cases_f, labels_f], cwd=repo)
check("freeze guard: refuses when a label was edited after the commit", not ok and "not committed" in msg or "changes" in msg, msg)

# a scripted judge run + resume
try:
    from evaluation.judge import OllamaJudge  # needs deepeval
except ImportError:
    OllamaJudge = None
if OllamaJudge is None:
    print("[SKIP] scripted judge run (deepeval is not installed here)")
else:
    class Reply:
        def __init__(self, c): self.content = c  # noqa: E704

    class Scripted:
        def __init__(self): self.calls = 0  # noqa: E704

        def complete(self, messages, tools=None, temperature=0.0, response_format=None):
            self.calls += 1
            return Reply('{"score": %d, "reason": "r%d"}' % (1 + self.calls % 5, self.calls))

    sc = Scripted()
    cases = [{"case_id": f"C{i:02d}", "question_sent_to_pipeline": "Q?", "draft": "A."} for i in range(1, 5)]
    out = tmp / "judge_runs.csv"
    rows = v.do_run(1, "scripted", metric_factory=lambda: OllamaJudge(client=sc), cases=cases, info={"commit": "abc", "commit_time": "t"}, runs_csv=out)
    check("judge run: one row per case with score, reason, settings and the labels commit", len(rows) == 4
          and all(r["judge_score"] != "" and r["labels_commit"] == "abc" and r["temperature"] == 0 for r in rows))
    calls = sc.calls
    rows2 = v.do_run(1, "scripted", metric_factory=lambda: OllamaJudge(client=sc), cases=cases, runs_csv=out)
    check("judge run: a second start of the same run scores nothing again (resume)", rows2 == [] and sc.calls == calls)
    by = v.scores_by_run(out)
    check("judge run: scores can be read back per run and case", sorted(by[1]) == ["C01", "C02", "C03", "C04"])
    with out.open(encoding="utf-8", newline="") as fh:
        check("judge run: the raw CSV has every column", list(next(csv.reader(fh))) == v.COLUMNS)
print(f"\n{passed} passed, {failed} failed")
sys.exit(0 if failed == 0 else 1)
