# METRICS.md — HW3 Part 2 Retrieval Quality Comparison

Computed from `raw/retrieval_results.jsonl` and `raw/chunk_stats.csv` by `scripts/build_metrics.py`.
Averaged across the 5 questions in `questions.yaml`, top-k = 5.

| Technique | Chunks | Avg chunk length | Top-1 cosine | Mean@k cosine | Recall@k | Mean retrieval latency (ms) |
|---|---|---|---|---|---|---|
| Token | 243 | 936.8 | 0.7291 | 0.6694 | 0.80 | 39.23 |
| Semantic | 99 | 2128.6 | 0.7169 | 0.6431 | 1.00 | 27.53 |
| Sentence window | 1288 | 163.6 | 0.6319 | 0.6448 | 0.80 | 105.27 |

## Confidently-scored retrieval that does not contain the answer

For **Question 5** ("What pathogen and contaminated product were linked in CDC's June 2026 investigation of the Listeria outbreak, and what were the final case counts, including deaths?"), the **Token** technique's rank-1 result scored store_score=0.7691 (cosine_sim=0.7869) but was retrieved from `fda_investigations_foodborne_outbreaks.txt`, not the expected `cdc_listeria_soft_cheese_june2026.txt`.

> Investigations Date Posted Reference # Pathogen or Cause of Illness Product(s) Linked to Illnesses (if any) Total Case Count Investigation Status Outbreak/ Even

_(Fill in: why the embedding model likely considered this similar — e.g. shared domain vocabulary, similar outbreak-report structure/boilerplate, same pathogen family, etc.)_
