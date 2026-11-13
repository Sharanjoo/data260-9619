"""HW10 Part 2: evaluate one or more requests of the Planner -> Writer -> Reviewer pipeline.

    python scripts/hw10_evaluate.py --trace-id <correlation_id> [--trace-id ...]     (collect from Kafka, then judge)
    python scripts/hw10_evaluate.py --from-bundles reports/hw10/raw/bundles.jsonl --trace-id <id>   (no Kafka needed)
    python scripts/hw10_evaluate.py --judge-model qwen3:4b ...

Collects plan + draft + final by correlation_id (original messages are saved to bundles.jsonl), scores plan quality, writer
helpfulness, final-answer helpfulness and the final-vs-draft difference with the local judge, appends the results to
reports/hw10/raw/evaluations.jsonl and prints them. The judge needs Ollama; Kafka is needed unless --from-bundles is used."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "code"))

from evaluation.collector import collect_from_kafka, load_bundles, save_bundles  # noqa: E402
from evaluation.evaluator import BUNDLES_PATH, EVALS_PATH, append_results, evaluate_bundle, load_results  # noqa: E402
from evaluation.judge import JUDGE_MODEL, OllamaJudge  # noqa: E402
from evaluation.rubrics import build_metrics  # noqa: E402

BANNER = "Sharan Lourduraj | SID4 9619 | DATA 260 HW10 Part 2 (pipeline evaluator)"


def show(r: dict) -> None:
    s = r["scores"]
    print(f"\ntrace_id: {r['trace_id']}   status: {r['status']}   judge: {r['judge_model']}   time: {r['evaluation_ms'] / 1000:.1f}s")
    print(f"question: {(r['question'] or '')[:110]!r}")
    print(f"  Plan Quality         {s['plan_quality']['score']}   {s['plan_quality']['reason'][:230]}")
    print(f"  Writer Helpfulness   {s['writer_helpfulness']['score']}   {s['writer_helpfulness']['reason'][:230]}   [trace_id {r['trace_id']}]")
    print(f"  Final Helpfulness    {s['final_helpfulness']['score']}   {s['final_helpfulness']['reason'][:230]}")
    print(f"  final answer: {(r['inputs']['final_answer'] or '')[:300]!r}")
    i = r["improvement"]
    print(f"  Final-vs-Draft       draft={i['draft_score']} final={i['final_score']} difference={i['difference']}")
    print(f"  interpretation: {i['interpretation']}")
    for k, v in r["errors"].items():
        print(f"  ERROR in {k}: {v}")
    if r["missing_parts"]:
        print(f"  missing parts: {r['missing_parts']}")


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trace-id", action="append", default=[], help="correlation_id of a finished request (repeatable)")
    ap.add_argument("--runs-file", default=None, help="evaluate every confirmed miss of a latency run (data/hw10/latency_runs.jsonl)")
    ap.add_argument("--skip-done", action="store_true", help="skip trace_ids that already have a result (resume a long run)")
    ap.add_argument("--from-bundles", default=None, help="load saved bundles instead of reading Kafka")
    ap.add_argument("--judge-model", default=JUDGE_MODEL)
    ap.add_argument("--timeout", type=float, default=45.0, help="seconds allowed for reading Kafka")
    args = ap.parse_args()
    print(BANNER, flush=True)
    if args.runs_file:
        for line in Path(args.runs_file).read_text(encoding="utf-8").splitlines():
            rec = json.loads(line) if line.strip() else {}
            if rec.get("phase") == "miss" and rec.get("kind_result") == "confirmed_miss":
                args.trace_id.append(rec["trace_id"])
    if args.skip_done:
        done = {r["trace_id"] for r in load_results(EVALS_PATH) if r.get("status") in ("ok", "partial")}
        args.trace_id = [t for t in args.trace_id if t not in done]
    if not args.trace_id:
        print("nothing to evaluate (no --trace-id, or all already done)")
        return 0
    if args.from_bundles:
        saved = load_bundles(Path(args.from_bundles))
        bundles = {t: saved.get(t) or {"trace_id": t, "missing": ["plan", "draft", "final"], "question": None}
                   for t in args.trace_id}
    else:
        got = await collect_from_kafka(args.trace_id, args.timeout)
        bundles = got["bundles"]
        save_bundles(bundles.values(), BUNDLES_PATH)
        print(f"collected {sum(1 for b in bundles.values() if not b['missing'])}/{len(bundles)} complete bundles from Kafka "
              f"(skipped malformed={got['stats']['malformed']}, duplicates={got['stats']['duplicates']}, "
              f"scan timeouts={got['stats']['timed_out']}); saved to {BUNDLES_PATH.relative_to(REPO)}")
    judge = OllamaJudge(model=args.judge_model)
    metrics = build_metrics(judge)
    results = []
    for tid in args.trace_id:
        r = evaluate_bundle(bundles[tid], metrics, judge.get_model_name())
        results.append(r)
        append_results([r])  # saved per request: a stopped run keeps what it finished
        show(r)
    print(f"\nsaved {len(results)} result(s) to {EVALS_PATH.relative_to(REPO)}; judge calls={judge.calls} failures={judge.failures}")
    return 0 if all(r["status"] == "ok" for r in results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
