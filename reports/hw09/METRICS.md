# HW9 METRICS

Sharan Lourduraj, SID4 9619, DOMAIN_ID 3 (grocery recall notices). Redis: `redis/redis-stack-server:7.4.0-v3` (RediSearch vector index, FLAT, COSINE, 384 dimensions, host port 46379), embeddings `sentence-transformers/all-MiniLM-L6-v2`. Parts 2 and 3 use the HW8 agents (Planner, Writer, Reviewer) with `qwen3:8b` via Ollama; Part 4 uses `qwen3:1.7b` as the Answering Agent (reason in Part 4). Every number below is copied from a saved file in `reports/hw09/raw/` or from `reports/hw09/RUN_LOG.txt`; the source is named in each section. Times are single runs on a laptop (HP Pavilion, 32 GB, no GPU), not benchmarks.

## Part 1: Redis view counter (`RUN_LOG.txt`, `scripts/test_hw9_part1.py`)

| Metric | Value |
|---|---|
| Record used | REC-015007 (recall_record id 15007), 25 accesses |
| Syncs to MySQL | after access 10 and access 20 (every 10th increment) |
| End state | Redis 25, MySQL `view_count` 20 (5 accesses not yet synced) |
| `scripts/test_hw9_part1.py` against real Redis and MySQL | 13/13 checks passed |

Known limit: the database holds a snapshot that can be up to 9 accesses behind Redis. When two processes sync at nearly the same time, an older count could be written after a newer one (the test only requires the value in MySQL to be a multiple of 10 that is at most the Redis count).

## Part 2: semantic cache in front of the HW8 pipeline (`raw/part2_summary.json`, `raw/part2_queries.jsonl`)

Threshold 0.85, 14 queries (7 new questions that should miss, 7 repeats that should hit), `qwen3:8b` behind the cache.

| Metric | Value |
|---|---|
| Queries served from the cache | 7 of 14, hit rate 50.0% |
| Queries that behaved as intended | 14/14 |
| Mean latency, served from cache | 153.34 ms (range 54.4 to 331.8 ms) |
| Mean latency, agents ran (miss) | 99,037 ms = 99.0 s (range 68.0 to 132.4 s) |
| Ratio | about 650 times faster on a hit |
| Exact repeats (3) | similarity 1.000 |
| Paraphrases (4) | similarity 0.861, 0.898, 0.940, 0.958 (all above 0.85, all hits) |
| New questions that came close | 0.806, 0.780, 0.754 (below 0.85, correctly misses) |

The hit rate of 50% is a property of how I built the 14 queries (half were repeats), not a prediction for real traffic.

## Part 3: threshold sweep, false hit, cost, stale answer

### 3.1 The cases (`data/hw09/cache_cases.yaml`, commit c76bf0e)

20 cached questions (units for even index, agency for odd) and 40 cases: 10 exact duplicates, 10 paraphrases, 10 look-alikes (C21 to C25 a sibling lot of the same product, C26 to C30 the same record asked for the other aspect) and 10 unrelated questions. The file was committed before any sweep output existed (`verify_hw09.py` checks this).

### 3.2 Agent pass and sweep (`raw/part3_agent_pass.jsonl`, `raw/part3_similarities.csv`, `raw/part3_sweep_cases.csv`, `raw/part3_sweep.json`)

The 50 distinct questions of the cases file were run through the agents once with the cache off (10:13 to 11:38 UTC, 85 minutes): 50/50 approved, mean agent latency 101.6 s (range 58.3 to 149.1 s, median 107.0 s). In 40/40 of the answers that have an expected fact the saved answer contains it. The sweep loads the 20 cached answers into Redis and searches each case in Redis (the search is timed for real). When a case is not served, its latency is the measured search time plus the agent latency of the same question from the agent pass. **This is a replay: the agents were not run 200 times.**

Nearest cached question, similarity by group (min / mean / max):

| Group | Min | Mean | Max |
|---|---|---|---|
| exact duplicate | 1.0000 | 1.0000 | 1.0000 |
| paraphrase | 0.7936 | 0.9186 | 0.9719 |
| look-alike | 0.8416 | 0.8971 | 0.9582 |
| unrelated | 0.2251 | 0.4975 | 0.6524 |

Sweep over 40 cases (20 should hit: 10 exact + 10 paraphrase; 20 should miss: 10 look-alike + 10 unrelated):

| Threshold | Hit rate | Correct hits | False hits | False-hit rate (of 20 should-miss) | False misses | Mean latency |
|---|---|---|---|---|---|---|
| 0.75 | 75.0% | 20 | 10 | 50% | 0 | 16.9 s |
| 0.80 | 72.5% | 19 | 10 | 50% | 1 | 20.1 s |
| 0.85 | 70.0% | 19 | 9 | 45% | 1 | 22.8 s |
| 0.90 | 55.0% | 17 | 5 | 25% | 3 | 39.3 s |
| 0.95 | 40.0% | 15 | 1 | 5% | 5 | 55.9 s |

Look-alikes (0.84 to 0.96) overlap paraphrases (0.79 to 0.97), so no threshold separates them. Every false hit is a look-alike. Raising the threshold removes false hits but also true hits, which raises mean latency.

### 3.3 One false hit in full (`raw/part3_false_hit.json`)

Case C23 (look-alike), similarity 0.9582, still a hit at 0.95. Cached: "How many units were affected by recall REC-018041 (Premium Bottled Juice (Lot 03035), Blue Ridge Pantry)?" Incoming: the same question for REC-015092 (Lot 00086, Blue Ridge Naturals). The cache returned 24,753 units; the database fact for REC-015092 is 35,574. The two questions share 13 of 16 words.

### 3.4 Cost model and threshold to ship (`raw/part3_cost.json`)

c_miss = mean agent latency 101.6 s x $1.00/hour (assumed server price) = $0.0282. c_false = $5.00 (assumed: one support contact, about 10 minutes at $30/hour). total = not served x c_miss + false hits x c_false.

| Threshold | Not served | False hits | Miss cost | False-hit cost | Total |
|---|---|---|---|---|---|
| 0.75 | 10 | 10 | $0.28 | $50.00 | $50.28 |
| 0.80 | 11 | 10 | $0.31 | $50.00 | $50.31 |
| 0.85 | 12 | 9 | $0.34 | $45.00 | $45.34 |
| 0.90 | 18 | 5 | $0.51 | $25.00 | $25.51 |
| 0.95 | 24 | 1 | $0.68 | $5.00 | $5.68 |

Threshold to ship: **0.95**. Sensitivity: the cheapest threshold stays 0.95 for c_false of $0.05, $0.50, $5 and $50 (at $0.05 the totals are close: 0.95 = $0.73, 0.90 = $0.76). Even at 0.95 one wrong answer is served, so a threshold alone is not enough; a check that the record code in the question matches the cached entry would remove the remaining case (not built). The `total_cost` field inside `part3_sweep.json` uses a placeholder price from an earlier step; `part3_cost.json` is the one used here.

### 3.5 Stale answer and invalidation (`raw/part3_stale.json`)

Record REC-016586, question "How many units were affected by recall REC-016586 ...?", units changed in MySQL from 5,445 to 8,445 (restored afterwards).

| Step | Latency | Result |
|---|---|---|
| 1. First ask (miss, agents) | 145.6 s | 5,445 units, answer cached with data version |
| 3. Ask again after the change, no version check | 59.4 ms | hit, **still 5,445 (stale)** |
| 4. Ask again with version check | 87.3 s | check took 14.0 ms, stale entry removed, agents re-ran, 8,445 units |
| 5. Ask again with version check | 287.8 ms | normal hit, 8,445 units |
| 6. Cost of the check, mean of 10 hits | 70.4 ms without, 99.9 ms with | +29.5 ms (about +42%) |

The data version is a hash of the answer-relevant fields of the record (not `updated_at`, because Part 1 rewrites `view_count` on the same row).

## Part 4: Answering Agent and Evaluator Agent (`raw/part4_*`, `data/hw09/`)

Data (synthetic, `scripts/build_hw9_part4_data.py`, seed 9619): 18 recall notices, 12 updated after publication (units, lot codes, states, refund deadline, status) and 6 unchanged; `training_data.json` 40 questions (notices 1 to 6), `validation_data.json` 14 (notices 7 to 12), `test_data.json` 20 (notices 13 to 18); the three files hold only `id` and `question`. Ground truth for the Evaluator is `reference_dataset.json`.

Model choice: `qwen3:8b` answered all 16 first training questions correctly (`raw/part4_train_qwen3-8b.jsonl`, mean 20.9 s), so no failure existed to learn from. The Answering Agent therefore uses `qwen3:1.7b` (temperature 0, seed 9619).

| Training run (`qwen3:1.7b`) | First attempt | After retry | Lessons created |
|---|---|---|---|
| Run 1, 16 questions (`..._run1.jsonl`) | 12/16 | 13/16 | 1 |
| Run 2, 16 questions, after widening the Evaluator's refusal wording (`..._run2_16q.jsonl`) | 14/16 | 15/16 | 0 |
| Run 3, 40 questions (`part4_train.jsonl`) | 34/40 (85%) | 39/40 (97.5%) | 3: L001 stale_value, L002 missing_value, L003 fabricated_answer |

Validation gate (`raw/part4_gate.json`; first attempt only, 14 questions, no-lesson baseline C0 = 11/14):

| Lesson | Alone | Fixed | Broke | Strict rule | Net rule |
|---|---|---|---|---|---|
| L001 stale_value | 12/14 | V08, V12 | V06 | reject | accept |
| L002 missing_value | 10/14 | V12 | V04, V06 | reject | reject |
| L003 fabricated_answer | 13/14 | V02, V08, V12 | V06 | reject | accept |
| L001 + L003 together | 13/14 | V02, V08, V12 | V06 | | accept |

The first version of the gate (strict: fix at least one, break none) rejected all three because every lesson changed the answer to V06 so that it dropped "do not eat". I then changed the rule to net gain (fixes minus breaks at least 1) after seeing this, and the strict result is kept in `raw/part4_gate_strict.json`. Accepted lessons: L001 and L003.

Four variants on the 20 test questions (`raw/part4_variants.json`):

| Variant | First attempt | Final | Mean attempts | Mean s/question |
|---|---|---|---|---|
| V1 baseline (no lessons, no retry) | 17/20 | 17/20 | 1.00 | 7.9 |
| V2 retry only | 16/20 | 19/20 | 1.20 | 8.8 |
| V3 lessons only | 19/20 | 19/20 | 1.00 | 6.8 |
| V4 lessons + retry | 19/20 | 20/20 | 1.05 | 6.7 |

V1 and V2 use the same first-attempt prompt but scored 17 and 16 (X04 passed once and failed once), so the model is not exactly repeatable and a one-question difference on 20 questions is within that noise. Demo (`raw/part4_demo.json`): the first answer was forced to the pre-update unit count (3,070); the Evaluator marked it `stale_value`, without the retry the user would have received it, with the retry attempt 2 gave 6,260 (the current value) in 12.7 s.

## Tests and verification

| Item | Result |
|---|---|
| `scripts/test_hw9_cache.py` (stand-ins for Redis/embedder/agents) | 26/26 |
| `scripts/test_hw9_sweep.py` | 22/22 |
| `scripts/test_hw9_part4.py` (scripted fake model, no Ollama) | 58/58 |
| `scripts/verify_hw09.py` / `make verify-hw09` | see `verification.json` (checks_passed / checks_total) |

The offline Part 4 tests check the logic of the Evaluator, lessons, retry loop, gate and variants with a scripted model; they are not evidence about `qwen3:1.7b`. The Part 4 numbers above come from the real runs.
