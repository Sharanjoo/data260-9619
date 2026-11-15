# HW10 METRICS

Sharan Lourduraj, SID4 9619, DOMAIN_ID 3 (grocery recall notices). Pipeline: HW8 Planner, Writer and Reviewer on Kafka, each running `qwen3:8b` through Ollama on CPU (HP Pavilion, 32 GB, no GPU), behind the HW9 Redis semantic cache (threshold 0.95). Judge: DeepEval GEval on a local Ollama `qwen3:8b`, temperature 0, thinking off, fixed evaluation steps, 1 to 5 rubric. All numbers below are recomputed from the raw files in `reports/hw10/raw/` and `data/hw10/` by `make verify-hw10`.

## Part 1: operations dashboard (`dashboard/`, `streamlit run dashboard/app.py`)

Three pages: Summary, Evaluation, Trace lookup. Data sources: `raw/spans.jsonl` (requests, hit rate, error rate, latency), `raw/evaluations.jsonl` (Part 2 scores), `raw/judge_validation.json` and `raw/judge_validation_per_case.csv` (Part 3). Files are loaded with `st.cache_data`, keyed on the file's modification time so a new run shows up without restarting; the trace-example lookup uses `st.cache_resource`. The Summary page states its window (a selectable time window: last 1 hour, 24 hours, 7 days, or all data in the file, defaulting to all data) and its data source on screen.

Summary page, all-time window, 133 requests (`raw/spans.jsonl`, 975 spans, first request 2026-11-13 00:45 UTC, last 04:11 UTC; this includes development test requests and the 23 overlapped requests described in Part 4):

| Metric | Value |
|---|---|
| Requests | 133 (113 with the cache on, 20 with the cache bypassed) |
| Cache hits | 50 = 44.2% of 113 cache-enabled requests |
| Cache misses | 63 = 55.8% (agents ran) |
| Errors | 1 = 0.75% (the failed trace, Part 4.2) |
| Latency, all requests | p50 70.3 s, p95 152.0 s |
| Latency, hits only | n=50, p50 62.8 ms, p95 314.5 ms |
| Latency, misses only | n=63, p50 99.7 s, p95 175.9 s |

The Summary page also shows the per-stage table for every complete cache miss in the window (62 requests: it adds the 11 misses of the discarded overlapped run, which ran slower, and the first live test request), so its figures differ from the Part 4.3 table below, which uses only the 50 confirmed misses of the latency run (for example Writer p95 55.6 s on the page versus 43.9 s in Part 4.3). The Evaluation page counts 51 evaluated requests, the 50 of the latency run plus the first live test request (`f4f5b265...`), so its means (3.35, 3.71, 3.73) differ slightly from the 50-request means in Part 2 (3.36, 3.72, 3.74).

Hits and misses are reported separately because one blended average (63.1 s) describes neither. The hit rate here is a property of the questions I chose to send (the latency run deliberately repeats some), not a prediction for real traffic.

## Part 2: DeepEval GEval evaluator (`code/evaluation/`, `scripts/hw10_evaluate.py`)

Plan, draft and final answer are joined by correlation_id from Kafka (`s9619_tasks`, `s9619_drafts`, `s9619_final`) and scored on 1 to 5. Every judge call has a 240 s timeout and one retry, and a judge failure is recorded as a null score rather than hanging the run. 50 confirmed-miss requests were evaluated: 50/50 complete bundles, 150 judge calls, 0 failures (`raw/bundles.jsonl`, `raw/evaluations.jsonl`).

| Stage | Mean | Median | Score counts (1 / 2 / 3 / 4 / 5) | Mean judge time |
|---|---|---|---|---|
| Plan Quality | 3.36 | 4 | 0 / 8 / 16 / 26 / 0 | 39.8 s |
| Writer Helpfulness | 3.72 | 4 | 0 / 1 / 14 / 33 / 2 | 41.6 s |
| Final Helpfulness | 3.74 | 4 | 0 / 1 / 14 / 32 / 3 | 23.6 s |

By question type (Final Helpfulness): 35 questions about a specific recall record averaged 4.03, 15 general questions averaged 3.07. Plan Quality is the weakest stage.

Final vs Draft: the Reviewer passes the draft through word for word, so the true difference is 0. The judge gave a difference of 0 for 45 of 50 requests, +1 for 3 and -1 for 2, on identical text. Those 5 are judge noise, not Reviewer improvement, and the evaluator prints that interpretation next to each one. The Writer and Final scores differ for 5 requests for the same reason.

## Part 3: judge validation against human labels

### 3.1 Cases and labels (`data/hw10/eval_cases.json`, `data/hw10/human_labels.csv`, commit 6861ada)

20 Writer drafts generated with the cache off (case C01 to C20, mixing record questions, general questions, an out-of-scope question and a nonexistent record) plus one whole-number label from 1 to 5 per case with a written note, from me alone, written with the labeling rubric in `data/hw10/LABELING_RUBRIC.md`. Both files were committed on 2026-11-12 18:32 PST. Every judge score row stores that commit hash, and the script refuses to run unless the files are committed and unchanged, so no label could have been adjusted after seeing a judge score. Human label distribution: 1 x 2, 2 x 1, 3 x 4, 4 x 4, 5 x 9.

### 3.2 Agreement (judge run 1 vs human, `raw/judge_validation.json`, `raw/judge_validation_per_case.csv`, `raw/judge_runs.csv`)

| Metric | Value |
|---|---|
| Spearman rank correlation (ties averaged), n=20 | 0.285 (p about 0.22, not significant at n=20) |
| Mean absolute difference | 1.05 points |
| Mean signed difference (judge minus human) | -0.15 |
| Exact match | 25% (5 of 20) |
| Within 1 point | 80% (16 of 20) |
| Largest difference | 3 points (C01 and C09) |
| Judge score distribution (1 / 2 / 3 / 4 / 5) | 0 / 0 / 7 / 12 / 1 |

The judge compresses everything into 3 and 4. The three drafts I scored 1, 1 and 2 (C01 told the shopper cooked recalled berries "may be safe to eat", C09 invented an announcement date, C13 made an unsupported size comparison) all received a 4 from the judge. It did not flag any of the failing drafts. Seven of my nine 5s got a 4, one a 3 (C04) and one a 5 (C18). The small negative bias (-0.15) is an average of large errors in both directions, so it hides the problem.

Illustration, with a pass line of 4 (chosen after seeing the scores, so it is an illustration and not a pre-declared test): the judge would pass 13 drafts, 3 of them drafts I rated 1 or 2, and block 7 drafts, 4 of which I rated 4 or higher.

### 3.3 Repeatability (runs 1, 2, 3, `raw/judge_runs.csv`)

0 of 20 cases changed between runs, mean absolute change 0.00, maximum 0. Agreement with the human labels is therefore identical in every run (Spearman 0.285 each time). This is expected at temperature 0: the same prompt gives the same score. It shows the judge is stable, not that it is right. Part 2 shows the other side: when the same text is presented under different metric names and inputs, the score moved by one point in 5 of 50 requests.

### Opinion: would I trust this judge to gate a deployment?

No. A gate must catch bad answers, and on my labels this judge scored the three worst drafts (unsafe advice, an invented date, an unsupported claim) at 4 out of 5, while giving four good drafts a 3. Its repeatability is perfect but its agreement with a person is weak (Spearman 0.285, off by a full point on average, and exact only 1 time in 4). It is usable as a rough trend line for catching a large regression across many requests, or as a triage signal that sends low-scoring cases to a human, but not as a pass/fail gate for safety-relevant recall advice.

Limits I can name: 20 cases and one labeler (me), so the correlation has wide uncertainty; the judge is the same model as the Writer, so it may favor the Writer's style; the judge sees the question and the draft but the labels also used my knowledge of the recall facts; the 3.2 analysis was fixed in advance as run 1 and 3.3 as runs 1 to 3.

## Part 4: tracing and latency

### 4.1 and 4.2 Spans and example traces (`raw/spans.jsonl`, `data/hw10/failed_trace.json`)

trace_id is the HW8 correlation_id, carried by every span from the cache lookup through Planner, Writer, Reviewer, queue waits and the evaluator. A span is one JSON line: trace_id, stage, start, end, duration_ms, status, error, attrs.

| Trace | trace_id | Outcome |
|---|---|---|
| Cache hit | `d401ec8b-c9b1-4e3d-b299-78272f09add7` | served from the cache in 95 ms, no agent spans |
| Cache miss | `e3307445-1bca-437b-a8b3-1edf0ec7533a` | all agent stages ran, answer approved |
| Failed | `08452391-e416-49b0-a8b0-bed7a3ba710b` | Writer failed 3 times (HTTP 404, model not found), dead-lettered, client timeout at 180 s |

Failed trace: cache lookup 63 ms ok, Planner 41.9 s ok, then three `writer` spans of 2.3 s, 2.1 s and 2.0 s with status error, a `dead_letter` span (134 ms, "gave up after 3 attempts"), and the `agent_pipeline` and `request` spans ended with timeout. The failure was produced without changing code: the normal Writer was stopped and a Writer instance pointed at the nonexistent model `no-such-model` was started in the same consumer group.

### 4.3 Latency of 50 confirmed cache misses (`data/hw10/latency_runs.jsonl`, `raw/latency_table.*`, `raw/latency_per_request.csv`)

Each miss was confirmed (similarity below 0.95, agents ran, answer approved). 78 questions were sent for 50 misses; 28 were answered by the cache (similarity 0.963 to 1.000) and excluded; the confirmed misses all scored below 0.93 against the nearest cached question. Warm-up request not measured. All 50 have a complete span set.

| Stage | p50 (ms) | p95 (ms) | Mean (ms) | % of end-to-end (mean) | % (p50) |
|---|---|---|---|---|---|
| Cache lookup | 86.4 | 175.8 | 95.5 | 0.1% | 0.1% |
| Planner | 28,744.2 | 42,814.6 | 29,334.9 | 32.2% | 30.8% |
| Writer | 33,869.0 | 43,920.4 | 33,540.3 | 36.9% | 36.3% |
| Reviewer | 30,168.5 | 35,782.3 | 27,907.4 | 30.7% | 32.4% |
| Queue wait (total of 4 hops) | 37.4 | 71.4 | 42.6 | 0.0% | 0.0% |
| Other (facts, Kafka send, cache store) | 48.8 | 168.5 | 66.6 | 0.1% | 0.1% |
| End-to-end (cache miss) | 93,223.2 | 117,799.6 | 90,987.4 | 100% | 100% |
| Evaluation (judge, outside the request path) | 103,450.1 | 133,741.8 | 105,021.2 | 115.4% | 111.0% |

Percentiles use linear interpolation. Share = mean stage time divided by mean end-to-end time of the same 50 requests. Evaluation runs after the answer is returned, so it is not part of the end-to-end time; it is shown for comparison and is why its share exceeds 100%.

Cache hits, reported separately (n=10 repeats of earlier questions, similarity 1.000): p50 74.8 ms, p95 106.7 ms, mean 73.9 ms. A hit is about 1,250 times faster than a miss at the median (74.8 ms vs 93.2 s).

Dominant contributor: the Writer, 36.9% of mean end-to-end time (p50 33.9 s, p95 43.9 s). The three LLM stages are close to equal thirds (32.2%, 36.9%, 30.7%) and together take 99.8% of the time; the cache lookup, queue waits and everything else add up to under half a second.

What to optimize first: the Writer is the largest single stage, so capping the length of its answer or using a smaller model there pays off most per stage. But the cheapest saving is the Reviewer: it takes about 28 to 30 s on every request and in all 50 requests returned the draft word for word, so a rule-based check (or skipping it when the draft already contains the safety sentence) would remove about 31% of the latency with no change to any answer. Both would be tested against the Part 3 labels before shipping, because the judge cannot be relied on to detect a quality drop.

Limits: queue wait is almost zero (42.6 ms) because the run sent one request at a time to an otherwise idle system, so it says nothing about behavior under concurrent load, where Kafka waits would grow. The cache held the answers of earlier requests, including 23 requests from an accidental second copy of the run script that were discarded (see below), so it had slightly more entries than a fresh cache.

Interrupted run, disclosed: at about 02:50 UTC I accidentally started the latency script in a second terminal. The two copies shared one pipeline, latencies rose from about 60 to 110 s to 150 to 190 s, and I stopped both. The 19 requests before the overlap (16 misses) were kept; the 23 overlapped rows were moved to `data/hw10/latency_runs.overlap_discarded.jsonl` and a full copy of the original log is `latency_runs.full_backup.jsonl`. The run was restarted from question 20 and reached 50 confirmed misses on a single copy. The 12 questions that were already cached by the discarded rows came back as hits and were excluded.
