"""HW3 Part 2: recompute the summary METRICS.md table from the raw retrieval data."""
import csv
import json
from collections import defaultdict
from pathlib import Path

RAW_DIR = Path("reports/hw03/raw")
RETRIEVAL_PATH = RAW_DIR / "retrieval_results.jsonl"
CHUNK_STATS_PATH = RAW_DIR / "chunk_stats.csv"
METRICS_PATH = Path("reports/hw03/METRICS.md")

TECHNIQUE_LABELS = {
    "token": "Token",
    "semantic": "Semantic",
    "sentence_window": "Sentence window",
}


def load_retrieval_rows():
    rows = []
    with open(RETRIEVAL_PATH, encoding="utf-8") as f:
        for line in f:
            rows.append(json.loads(line))
    return rows


def load_chunk_stats():
    stats = {}
    with open(CHUNK_STATS_PATH, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            stats[row["technique"]] = row
    return stats


def main():
    rows = load_retrieval_rows()
    chunk_stats = load_chunk_stats()

    by_technique = defaultdict(list)
    for r in rows:
        by_technique[r["technique"]].append(r)

    summary = {}
    for tname, trows in by_technique.items():
        by_question = defaultdict(list)
        for r in trows:
            by_question[r["question_id"]].append(r)

        top1_cosines = []
        mean_at_k_cosines = []
        latencies = []
        recall_hits = []
        for qid, qrows in by_question.items():
            qrows_sorted = sorted(qrows, key=lambda r: r["rank"])
            top1_cosines.append(qrows_sorted[0]["cosine_sim"])
            mean_at_k_cosines.append(sum(r["cosine_sim"] for r in qrows_sorted) / len(qrows_sorted))
            latencies.append(qrows_sorted[0]["retrieval_latency_ms"])
            recall_hits.append(1 if qrows_sorted[0]["hit_expected_source_in_topk"] else 0)

        summary[tname] = {
            "chunks": chunk_stats[tname]["num_chunks"],
            "avg_chunk_length": float(chunk_stats[tname]["avg_chunk_length_chars"]),
            "top1_cosine": sum(top1_cosines) / len(top1_cosines),
            "mean_at_k_cosine": sum(mean_at_k_cosines) / len(mean_at_k_cosines),
            "recall_at_k": sum(recall_hits) / len(recall_hits),
            "mean_latency_ms": sum(latencies) / len(latencies),
        }

    # Find the strongest "confidently scored but wrong" retrieval across all techniques:
    # highest store_score among rows where the retrieved chunk's source file is NOT
    # the expected source for that question.
    wrong_rows = [r for r in rows if r["source_file"] != r["expected_source_file"]]
    wrong_rows.sort(key=lambda r: (r["store_score"] if r["store_score"] is not None else -1), reverse=True)
    top_wrong = wrong_rows[0] if wrong_rows else None

    # --- Print summary to console ---
    print(f"{'Technique':<18}{'Chunks':<9}{'AvgLen':<10}{'Top-1cos':<11}{'Mean@kcos':<12}{'Recall@k':<10}{'Latency(ms)':<12}")
    for tname in ["token", "semantic", "sentence_window"]:
        s = summary[tname]
        print(f"{TECHNIQUE_LABELS[tname]:<18}{s['chunks']:<9}{s['avg_chunk_length']:<10.1f}"
              f"{s['top1_cosine']:<11.4f}{s['mean_at_k_cosine']:<12.4f}{s['recall_at_k']:<10.2f}{s['mean_latency_ms']:<12.2f}")

    if top_wrong:
        print(f"\nStrongest confidently-wrong retrieval:")
        print(f"  Question {top_wrong['question_id']}: {top_wrong['question']}")
        print(f"  Technique: {top_wrong['technique']}, rank {top_wrong['rank']}")
        print(f"  store_score={top_wrong['store_score']:.4f}, cosine_sim={top_wrong['cosine_sim']:.4f}")
        print(f"  Retrieved from: {top_wrong['source_file']}  (expected: {top_wrong['expected_source_file']})")
        print(f"  Preview: {top_wrong['preview']}")

    # --- Write METRICS.md ---
    lines = [
        "# METRICS.md — HW3 Part 2 Retrieval Quality Comparison",
        "",
        "Computed from `raw/retrieval_results.jsonl` and `raw/chunk_stats.csv` by `scripts/build_metrics.py`.",
        "Averaged across the 5 questions in `questions.yaml`, top-k = 5.",
        "",
        "| Technique | Chunks | Avg chunk length | Top-1 cosine | Mean@k cosine | Recall@k | Mean retrieval latency (ms) |",
        "|---|---|---|---|---|---|---|",
    ]
    for tname in ["token", "semantic", "sentence_window"]:
        s = summary[tname]
        lines.append(
            f"| {TECHNIQUE_LABELS[tname]} | {s['chunks']} | {s['avg_chunk_length']:.1f} | "
            f"{s['top1_cosine']:.4f} | {s['mean_at_k_cosine']:.4f} | {s['recall_at_k']:.2f} | "
            f"{s['mean_latency_ms']:.2f} |"
        )

    lines.append("")
    lines.append("## Confidently-scored retrieval that does not contain the answer")
    lines.append("")
    if top_wrong:
        lines.append(
            f"For **Question {top_wrong['question_id']}** (\"{top_wrong['question']}\"), the "
            f"**{TECHNIQUE_LABELS[top_wrong['technique']]}** technique's rank-{top_wrong['rank']} result "
            f"scored store_score={top_wrong['store_score']:.4f} (cosine_sim={top_wrong['cosine_sim']:.4f}) "
            f"but was retrieved from `{top_wrong['source_file']}`, not the expected "
            f"`{top_wrong['expected_source_file']}`."
        )
        lines.append("")
        lines.append(f"> {top_wrong['preview']}")
        lines.append("")
        lines.append(
            "_(Fill in: why the embedding model likely considered this similar — e.g. shared domain "
            "vocabulary, similar outbreak-report structure/boilerplate, same pathogen family, etc.)_"
        )
    else:
        lines.append("No wrong-source retrieval found in the top-k for any question — see console output.")

    METRICS_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nWrote {METRICS_PATH}")


if __name__ == "__main__":
    main()