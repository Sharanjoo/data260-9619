# HW8 METRICS

Sharan Lourduraj, SID4 9619, DOMAIN_ID 3 (grocery recall notices). Kafka: `apache/kafka:3.9.2`, one broker (KRaft), `aiokafka` 0.15 client. Every number below is copied from a saved file in `reports/hw08/raw/` or from `reports/hw08/RUN_LOG.txt`; the source is named in each section. Times are single runs on a laptop (HP Pavilion, 32 GB, no GPU), not benchmarks.

## Part 1: request/response over Kafka (`RUN_LOG.txt`, `raw/homework_demo.json`)

| Metric | Value |
|---|---|
| Topics used by the entity service | 2 (`s9619_entity_requests`, `s9619_entity_responses`) |
| Demo checks passed (CREATE, GET, correlation_id kept) | 5/5 |
| Error cases that kept the correlation_id | 3/3 (missing field 422, unknown id 404, unknown operation 422) |
| CREATE: API sent the request to the API returned | 96 ms (00:57:59.420 to 00:57:59.516) |
| GET: same measurement | 7 ms (00:57:59.922 to 00:57:59.929) |
| Error cases: same measurement | 9 ms, 11 ms, 13 ms |

The first request after the demo started took 96 ms; the later requests took 7 to 13 ms. I did not investigate why the first one is slower.

## Part 2: Planner, Writer, Reviewer (`raw/part2_journey.log`, `raw/part2_final.json`)

One real run with `qwen3:8b` (CPU), correlation_id `77c63d87-a42c-4d6f-abe5-59c5d0868438`.

| Stage | Time | Topic written |
|---|---|---|
| Planner (1 model call) | 43.4 s | `s9619_tasks`, partition 1, key `frozen-berries-lot-1` |
| Writer (1 model call) | 26.1 s | `s9619_drafts` |
| Reviewer (1 model call + 3 rule checks) | 32.3 s | `s9619_final`, status `approved` |
| Whole journey (question sent to final received) | 101.8 s | |

The correlation_id appears unchanged in the client, Planner, Writer and Reviewer logs. The model call dominates the time; each Kafka hop between stages took 1 to 4 ms (client to Planner 3 ms, Planner to Writer 4 ms, Writer to Reviewer 2 ms, Reviewer to client 1 ms, from the log timestamps).

## Part 3: failure tests (`raw/part3_*.json`, `raw/part3_logs/`, `RUN_LOG.txt`)

Run with the agents in deterministic fast mode (no model call), so each test takes seconds. Every test is run twice with the same messages: protection off ("before") and on ("after").

| Test | Before (protection off) | After (protection on) |
|---|---|---|
| I Duplicate delivery (same correlation_id sent twice) | 2 tasks, 2 drafts, 2 final answers (side effects repeated) | 1 task, 1 draft, 1 final answer; Planner logged `DUPLICATE ... skipped` |
| II Writer killed mid-work | offset committed on receipt: after restart 0 drafts, message lost | offset committed after success: restarted Writer received the same message again (partition 1 offset 31) 9.9 s after the first delivery, 1 draft and 1 final |
| III Poison message (plan is not a list) followed by 2 good messages | retry forever: 30 failed attempts over about 14.5 s, 0 of 2 good messages processed, 0 dead letters | 3 attempts in 1.0 s, 1 message on `s9619_dead_letter`, 2 of 2 good messages processed (first one 67 ms after the dead-letter write) |
| IV Ordering, 20 messages, 2 partitions, 2 Writers | no key: 5 out-of-order pairs; 4 of 5 recall notices split across both partitions | key = recall notice: 0 out-of-order pairs; every notice in one partition |

Notes on how to read these numbers:

- Test I "after": the replay reaches the Planner's idempotency check first, so nothing is sent downstream. The "before" run shows the cost of the missing check at every stage.
- Test II "after": the 9.9 s is the broker's consumer session timeout; the dead Writer's partition is only handed to the restarted Writer after that. The message is delivered twice in total (once to the dead Writer, once to the new one), which is why the idempotency check from test I matters.
- Test IV "before": without a key the producer chooses partitions at random, so the 5 out-of-order pairs is what this run showed (an earlier, unrecorded run of the same test showed 4). The keyed run is deterministic: Kafka always sends the same key to the same partition. With the key, the load is not even: 12 messages went to partition 0 and 8 to partition 1, because the five notices are not equally busy.
- Test IV messages come from `random.Random(VERIFY_SEED=269619)`: 20 messages over 5 recall notices (spinach-bag 6, chicken-nuggets 6, frozen-berries 5, peanut-butter 2, infant-formula 1).

## Tests and verification

| Item | Result |
|---|---|
| `scripts/test_kafka_hw08.py` (in-memory broker: validation, worker, round trip, API wrapper, health check) | 68 checks passed, 0 failed |
| `scripts/test_agents_hw08.py` (in-memory broker: journey, duplicates, kill and restart, poison and dead-letter, ordering) | 40 checks passed, 0 failed |
| `scripts/verify_hw08.py` / `make verify-hw08` | see `verification.json` (checks_passed / checks_total) |

The in-memory tests check our own logic quickly; they are not evidence about Kafka itself. The Kafka behaviour (consumer-group redelivery after a kill, partition assignment, key-to-partition routing) is shown only by the real runs above.
