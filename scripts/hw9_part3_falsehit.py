"""HW9 Part 3.3: show one false hit in full (the highest-similarity one at the chosen threshold; nothing is staged).

    python scripts/hw9_part3_falsehit.py [--threshold 0.85]

Reads the sweep output; writes raw/part3_false_hit.json."""
from __future__ import annotations

import argparse
import csv
import difflib
import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "code"))

from cache_layer.config import BANNER  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "reports" / "hw09" / "raw"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--threshold", type=float, default=0.85)
    args = parser.parse_args()
    print(BANNER + " | hw9_part3_falsehit", flush=True)
    doc = yaml.safe_load((ROOT / "data" / "hw09" / "cache_cases.yaml").read_text(encoding="utf-8"))
    cases = {c["id"]: c for c in doc["cases"]}
    answers = {}
    for line in (RAW / "part3_agent_pass.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            if row["status"] == "approved":
                answers[row["query"]] = row["answer"]
    with (RAW / "part3_sweep_cases.csv").open(encoding="utf-8") as fh:
        rows = [r for r in csv.DictReader(fh) if abs(float(r["threshold"]) - args.threshold) < 1e-9 and r["false_hit"] == "True"]
    if not rows:
        print(f"no false hit at threshold {args.threshold}; try a lower threshold")
        return 1
    rows.sort(key=lambda r: -float(r["similarity"]))
    r = rows[0]
    case = cases[r["id"]]
    cached_q, incoming_q = r["nearest_query"], case["query"]
    cached_a, correct_a = answers[cached_q], answers[incoming_q]
    sm = difflib.SequenceMatcher(None, cached_q.split(), incoming_q.split())
    changed = [(" ".join(cached_q.split()[i1:i2]), " ".join(incoming_q.split()[j1:j2]))
               for tag, i1, i2, j1, j2 in sm.get_opcodes() if tag != "equal"]
    shared = sum(b.size for b in sm.get_matching_blocks())
    print(f"false hits at threshold {args.threshold}: {len(rows)}; showing the one with the highest similarity\n")
    print(f"case {case['id']} ({case['group']}, labeled '{case['expected']}')   similarity = {float(r['similarity']):.4f}\n")
    print(f"cached query:   {cached_q}")
    print(f"incoming query: {incoming_q}\n")
    print(f"cached answer (what the cache returned):\n  {cached_a}\n")
    print(f"correct answer (the agents' answer to the incoming query):\n  {correct_a}\n")
    print(f"database fact that makes it correct: {case.get('fact')}\n")
    print(f"words shared: {shared} of {len(cached_q.split())} / {len(incoming_q.split())}; the words that differ:")
    for a, b in changed:
        print(f"  cached: {a!r:<45} incoming: {b!r}")
    (RAW / "part3_false_hit.json").write_text(json.dumps({
        "threshold": args.threshold, "case": case["id"], "group": case["group"], "similarity": float(r["similarity"]),
        "cached_query": cached_q, "incoming_query": incoming_q, "cached_answer": cached_a, "correct_answer": correct_a,
        "fact": case.get("fact"), "differing_words": changed, "false_hits_at_threshold": len(rows)}, indent=2,
        ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
