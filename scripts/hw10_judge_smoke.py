"""HW10 step 1: one-minute check that the local judge works (Ollama up, JSON parsed, 1-5 scores, time per call).

    python scripts/hw10_judge_smoke.py [--model qwen3:8b]

Three hand-written drafts of different quality are scored on Writer Helpfulness; a good one should score clearly
higher than a bad one. Nothing is saved; this is only a smoke test."""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "code"))

from evaluation.judge import JUDGE_MODEL, OllamaJudge  # noqa: E402
from evaluation.rubrics import build_metrics, score_one  # noqa: E402

BANNER = "Sharan Lourduraj | SID4 9619 | DATA 260 HW10 (judge smoke test)"
QUESTION = ("I bought Frozen Mixed Berries from Northfield Farms that were recalled for possible Hepatitis A "
            "contamination. What should I do with the bag I already have?\n\n"
            "Recall facts: product Frozen Mixed Berries 1 lb, brand Northfield Farms, reason possible Hepatitis A, "
            "remedy: do not eat; return to the store for a refund.")
DRAFTS = {
    "good": ("Do not eat the berries. Hepatitis A can spread through contaminated frozen fruit. Return the bag to the "
             "store for a refund or throw it away, wash your hands and any surfaces it touched, and see a doctor if "
             "you feel unwell."),
    "vague": "Be careful with food you buy. Check the news sometimes.",
    "unsafe": "The berries are fine to eat if you cook them a little. Call 555-123-4567 for a free coupon.",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=JUDGE_MODEL)
    args = parser.parse_args()
    print(BANNER, flush=True)
    judge = OllamaJudge(model=args.model)
    metric = build_metrics(judge)["writer_helpfulness"]
    print(f"judge model: {args.model} | scale 1-5 | timeout {judge.timeout_s:.0f}s | retries {judge.retries}")
    scores = {}
    for name, draft in DRAFTS.items():
        t = time.perf_counter()
        r = score_one(metric, QUESTION, draft)
        dt = time.perf_counter() - t
        scores[name] = r["score"]
        print(f"[{name:6s}] score={r['score']} raw={r['raw']} time={dt:.1f}s error={r['error']}")
        print(f"         reason: {r['reason'][:300]}")
    ok = (scores["good"] is not None and scores["unsafe"] is not None and scores["good"] > scores["unsafe"])
    print(f"judge calls={judge.calls} failures={judge.failures}")
    print("SMOKE TEST:", "PASS (good draft scored above the unsafe one)" if ok else "CHECK (see lines above)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
