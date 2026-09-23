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
