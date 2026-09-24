# HW4 Metrics — SID4 9619

## Part 3: N+1 Measurement and Query Tuning

Seed data: 200 `recall_source` rows, 5,000 `recall_record` rows, seeded with `SEED = 9619` (`scripts/seed_hw04.py --reset`). Measured with `scripts/measure_n1.py` — 30 requests per (page size × version) combination, 180 requests total, 2 warm-up requests discarded per combination. `SQL stmts/req` is read from the `X-SQL-Query-Count` response header (a per-request SQL statement counter installed as FastAPI middleware in `code/main.py`); latencies are client-observed wall-clock round trips.

| Page size | Version | SQL stmts/req | p50 (ms) | p95 (ms) | p99 (ms) |
| --- | --- | --- | --- | --- | --- |
| 10  | naive | 13  | 62.79  | 77.65  | 81.20  |
| 10  | fixed | 3   | 36.07  | 49.86  | 51.06  |
| 50  | naive | 47  | 144.53 | 207.96 | 522.14 |
| 50  | fixed | 3   | 31.45  | 48.18  | 48.85  |
| 200 | naive | 131 | 384.89 | 489.56 | 499.11 |
| 200 | fixed | 3   | 36.32  | 51.89  | 83.85  |

Raw per-request data (all 180 requests): `reports/hw04/raw/n1_measurements.jsonl`. Machine-readable summary: `reports/hw04/raw/n1_summary.csv`.

### Speed-up at each page size (p50)

| Page size | naive p50 | fixed p50 | Speed-up |
| --- | --- | --- | --- |
| 10  | 62.79 ms  | 36.07 ms | 1.74x |
| 50  | 144.53 ms | 31.45 ms | 4.60x |
| 200 | 384.89 ms | 36.32 ms | 10.60x |

### Why the speed-up grows as page size increases

The fixed endpoint (`GET /api/hw4/records-fixed`) issues exactly **3** SQL statements per request no matter the page size: one query to look up the session token, one to load the user, and one single `LEFT JOIN` query (via SQLAlchemy's `joinedload`) that fetches every record's related `recall_source` row in the same round trip. Its latency is therefore essentially flat (~31–36 ms p50) across all three page sizes.

The naive endpoint (`GET /api/hw4/records`) issues the same 2 auth queries, 1 list query, plus **one extra lazy-load query for every *distinct* `source_id` value present on that page** — not one per row. Because there are only 200 possible sources and each of the 5,000 records was assigned one uniformly at random, a page of `N` rows only touches `~200 × (1 − (199/200)^N)` distinct sources (a birthday-problem-style collision curve): SQLAlchemy's per-session identity map caches an already-loaded `RecallSource` object, so repeat hits on the same source don't re-query. That predicts ~10 distinct sources at page size 10 (10 extra queries, 13 total — matches exactly), ~44 at page size 50 (47 total — matches), and ~128 at page size 200 (131 total — matches).

So query count for the naive endpoint grows with page size, just sub-linearly rather than as a flat `N+1`. Each of those extra queries still costs a real round trip plus statement-parsing overhead on top of the fixed cost every request pays, so total latency grows with query count while the fixed endpoint's cost stays constant — which is exactly why the ratio between them widens from ~1.7x at page 10 to ~10.6x at page 200: naive's extra cost compounds with page size, fixed's doesn't.

### Step 8: adding an index

`recall_record.source_id` was **not** chosen for indexing: InnoDB automatically creates an index on any column used as a foreign key (required for constraint-checking), so `source_id` already had an implicit index from the moment `recall_record` was created — indexing it again would show no real before/after difference in `EXPLAIN`.

Instead, `scripts/add_index_hw04.py` adds `idx_recall_record_product_name` on `recall_record.product_name` and demonstrates a realistic "look up a recall by product name" query before and after:

**Before** (`EXPLAIN SELECT ... WHERE product_name = 'Fresh Yogurt (Lot 02501)'`):

| type | key | rows examined | Extra |
| --- | --- | --- | --- |
| ALL | *(none)* | 5000 | Using where |

**After:**

| type | key | rows examined | Extra |
| --- | --- | --- | --- |
| ref | idx_recall_record_product_name | 1 | *(none)* |

Before the index, MySQL had no way to locate matching rows except a full table scan (`type: ALL`), examining all 5,000 rows to find the one matching `product_name`. After adding the index, MySQL uses `idx_recall_record_product_name` directly (`type: ref`), going straight to the matching row — estimated rows examined drops from 5,000 to 1. Full detail: `reports/hw04/raw/explain_before_after.json`.

---

## Part 4: Grounded RAG Question-Answering System

Corpus: `data/hw03_corpus` (25 CDC/FDA food-safety/recall documents, reused from HW3 -- well past the 5-document minimum). Chunking: LlamaIndex `TokenTextSplitter(chunk_size=500, chunk_overlap=50)` -> 128 chunks. Embeddings: `sentence-transformers/all-MiniLM-L6-v2`. Vector store: FAISS (`IndexFlatIP` over L2-normalized vectors, i.e. cosine similarity). Generation: `qwen3:8b` via Ollama (`src/model_client.py`, `temperature=0`, thinking disabled). Full script: `code/rag.py`. Raw output: `reports/hw04/raw/rag_question_results.jsonl` (retrieval + all 3 configs' answers per question), `reports/hw04/raw/rag_k_sweep.json`, `reports/hw04/raw/rag_eval_table.csv`.

### Three-configuration comparison

| Q | Type | (A) No-RAG | (B) Basic-RAG (top-3 raw) | (C) Context-engineered |
| --- | --- | --- | --- | --- |
| Q1 | one chunk | Correct, generic phrasing | Correct, matches FDA wording closely | Correct, cited (Source 1) throughout |
| Q2 | two chunks | **Wrong** -- claims neither outbreak is documented | **Wrong** -- soft-cheese numbers hallucinated (12/10/1, actual 15/14/1); deli-meats omitted | Refused -- retrieval never surfaced the deli-meats source, so it correctly declined rather than guessing |
| Q3 | similar across docs | **Wrong** -- names FALCPA/Jan 2006 (actual: FASTER Act/Jan 2023) | Correct -- FASTER Act, Jan 2023 | Correct, cited (Source 2) |
| Q4 | ambiguous | Reasonable, generic | Reasonable, cites a real oyster-outbreak stat | Reasonable, correctly synthesizes 2 distinct sources with citations |
| Q5 | not in docs (must refuse) | Avoids false specifics, but not a *grounded* refusal -- reasoning from absence of training data, not from context | Notes context lacks the info, but no strict refusal format | **Exact required refusal phrase** |
| Q6 | unrelated (must refuse) | **Wrong** -- confidently answers "Canberra" from outside knowledge | Inconsistent -- says it can't answer from context, then answers anyway | **Exact required refusal phrase**, 0.00s (auto-refused: 0/5 retrieved chunks passed the relevance filter, so the LLM was never even called) |

Ground truth used to grade Q2 (verified directly against the source files, not the model's own numbers): soft cheese (June 2026) = 15 illnesses, 4 states, 14/14 hospitalized, 1 death (Maryland); deli meats (2024) = 61 cases, 60 hospitalizations, 10 deaths.

### k-sweep (Q2, the two-chunk question)

| k | Both expected sources retrieved? | Answer |
| --- | --- | --- |
| 1 | No | Refused |
| 3 | No | Refused |
| 5 | No (soft-cheese source entered; deli-meats source never did) | Answered soft-cheese correctly (15 illnesses, 14 hospitalizations, 1 death, cited), still correctly silent on deli-meats |

More context helped, but only up to a point: k=1 and k=3 missed the specific chunk containing the soft-cheese numbers entirely, so the grounding rule correctly forced a full refusal. At k=5 that chunk finally entered the pool and Config C answered the half it could support -- but the deli-meats 2024 document never appeared even at k=5, so widening k further would likely be needed (or a retrieval fix) to answer the full question. This is the "more context is not always better context" lesson in reverse: here more context helped rather than hurt, but it could not fully compensate for a retrieval gap, and irrelevant chunks never became a problem for this particular question (all 5 pooled chunks stayed topically on-subject).

### Evaluation summary (aggregated across all 6 questions)

| Config | Accuracy (answerable Qs, 1-4) | Faithfulness | Format compliance | Robustness (Q5/Q6 refusal correctness) |
| --- | --- | --- | --- | --- |
| (A) No-RAG | 2/4 correct | Low -- hallucinated a law/date on Q3, claimed real outbreaks were undocumented on Q2 | N/A (no format required) | 0/2 -- answers from outside knowledge instead of refusing |
| (B) Basic-RAG | 3/4 correct | Medium -- mostly faithful to retrieved text, but fabricated specific numbers on Q2 when the exact figures weren't in its 3 raw chunks | N/A (no format required) | Partial -- hedges but doesn't reliably refuse (Q6 answers anyway after saying it can't) |
| (C) Context-engineered | 3/4 correct, 1 appropriately refused rather than guessing | High -- never states a fact its cited sources don't contain | 100% -- cites sources on every non-refusal answer, exact refusal sentence both times it's required | 2/2 -- exact refusal phrase on both Q5 and Q6 |

### Written analysis (context engineering: what helped, what didn't, and why)

Retrieval quality was strong for topically distinct, well-represented questions and weak when two facts needed to come from different documents with different phrasing. Q1 (single-chunk) retrieved the correct source at rank 1 with a clear score gap (0.67 vs. 0.50 for the next-best chunk), and all three configurations answered it correctly. Q3 (allergen law) also retrieved cleanly, pulling from both `fda_food_allergies.txt` and `fda_allergen_labeling_qa_edition5.txt` -- exactly the "similar information across documents" case the question was designed to test -- and Config C's de-duplication filter correctly kept one representative chunk from each rather than two near-identical ones. Q2 (needs two chunks) is where retrieval genuinely struggled: despite an explicit two-part question naming both outbreaks, the top-5 pool never surfaced `cdc_listeria_delimeats_2024.txt` at all, even though it is clearly the single most relevant document by keyword. The k-sweep shows more context did eventually help -- k=1 and k=3 both refused outright, and only at k=5 did a chunk with the soft-cheese outbreak's actual numbers enter the context, letting Config C answer that half correctly while still (correctly) declining the deli-meats half. The deli-meats chunk never appeared even at k=5, so more context helped up to a point but could not fix a retrieval miss entirely.

Context-engineering changes that helped: de-duplication and source labeling made Config C's citations traceable and correct on every question where it answered (Q1, Q3, Q4). The relevance filter (drop chunks scoring under 0.20, or more than 0.15 below the top hit) worked perfectly for Q6 -- every retrieved chunk scored under 0.11, so Config C refused instantly without even calling the model. It did not fire for Q5, though: the retrieved chunks (all from the FDA outbreak-index table) scored 0.62-0.64 since they are topically about "outbreak investigations," just not about ground beef specifically. The refusal there came entirely from the grounding-rule instruction, not the score filter -- a useful finding: topical similarity and actual answerability are different things, and a pure similarity threshold will miss cases where the LLM's own judgment is what's actually needed.

The model did not hallucinate on Q5 or Q6 under Config C -- both got the exact required refusal sentence, with zero latency on Q6 since no chunk survived filtering. It did hallucinate without grounding: No-RAG invented a wrong law and date for Q3 (FALCPA/2006 instead of FASTER Act/2023) and wrongly claimed the Q2 outbreaks were undocumented; Basic-RAG partially fixed this but still fabricated specific numbers on Q2 (12/10/1 instead of the real 15/14/1) because nothing forced it to stick to what the retrieved text actually said. Overall: retrieval quality set a ceiling Config C could not exceed (Q2), context quality (de-duplication + labeling) improved traceability where retrieval succeeded, and the grounding-rule prompt -- not retrieval score alone -- was what actually prevented fabrication.
