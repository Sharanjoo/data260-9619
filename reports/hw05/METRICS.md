# HW5 METRICS.md

SID4=9619, SEED=9619, VERIFY_SEED=269619, PORT_BASE=8619, PREFIX=s9619,
DOMAIN_ID=3.

## Part 3.20 - Fault Injection Results

Retry policy: `max_retries=3` (4 total attempts), `timeout_s=0.25`,
exponential backoff `base_delay_s=0.05` capped at `max_delay_s=0.4` with
+/-25% jitter. 50 calls per rate, 150 calls total, seeded with
`VERIFY_SEED=269619` (fresh per rate, reproducible run to run). Raw
per-call records: `reports/hw05/raw/fault_injection_raw.csv`. Produced by
`scripts/fault_injection_hw05.py` against the live `s9619_rel` database.

| Injected failure rate | Success rate | Mean latency (ms) | p99 latency (ms) |
|---|---|---|---|
| 0% | 100.00% | 37.82 | 102.59 |
| 20% | 100.00% | 139.36 | 949.71 |
| 50% | 90.00% | 450.94 | 1414.16 |

### Part 3.21 - Is this retry policy suitable for an interactive assistant?

At 0% injected failure the policy adds essentially no overhead (37.8ms
mean, in line with a single fast indexed query). At 20%, every one of the
50 calls still eventually succeeded -- with 4 attempts available, the
chance of 4 consecutive failures at a true 20% per-attempt rate is only
0.2^4 = 0.16%, so near-100% success is expected, but the cost is real:
mean latency almost quadruples (37.8ms -> 139.4ms) and p99 balloons to
950ms, because a meaningful fraction of calls now pay for one retry's
backoff delay plus a second attempt. At 50%, the policy is no longer
hiding the underlying unreliability from the user: 10% of calls still
surface as a failure to the caller even after using the full retry budget,
mean latency is up 12x over the 0% baseline (450.9ms), and the worst calls
take 1.4 seconds (p99).

For an interactive assistant -- where a person is waiting on the other end
of each tool call -- this policy is a reasonable fit **up to roughly the
20% failure-rate regime**: it successfully converts a one-in-five chance
of failure into near-certain success, and even its p99 (under a second) is
within what a user will tolerate for a single backend call inside a
larger response. At 50%, though, the 1.4-second p99 and the fact that one
in ten calls still fails outright make it a weaker fit for a synchronous,
in-the-moment interaction: a user watching a single call take over a
second, or getting an outright error one time in ten, would notice. The
retries are doing real work at 50% (90% success vs. what would be a flat
50% success with zero retries), but the latency cost of getting there is
the kind of thing that benefits from being backgrounded or streamed rather
than blocking a chat turn.

### How this policy would change for batch processing

Batch processing can trade latency for reliability in a way an interactive
session cannot, so the main levers would move in the opposite direction
from what you'd want for responsiveness:

- **More retries.** `max_retries=3` (4 attempts) was sized to keep p99
  under ~1.5s for an interactive call. In batch, nothing is waiting
  synchronously on any single call, so raising this to 6-8 attempts would
  push the 50%-failure-rate success rate from 90% much closer to 99%+
  (failure probability drops from 0.5^4=6.25% to 0.5^8=0.4%), at the cost
  of a slower worst case per item -- acceptable when the job runs
  unattended.
- **Longer timeout per attempt.** 0.25s was chosen to fail fast for a
  live user. A batch job can afford to wait several seconds per attempt
  before giving up, which also reduces false-positive timeouts on
  attempts that were actually going to succeed a little slowly rather
  than genuinely hang.
- **Larger backoff ceiling.** `max_delay_s=0.4` keeps backoff short enough
  that a human isn't sitting through multi-second pauses. In batch, a
  `max_delay_s` of 5-30 seconds (still exponential, still jittered) spaces
  out retries enough to let a transient outage on the other end actually
  recover, rather than hammering it every few hundred milliseconds.

The net effect: interactive = few retries, short timeout, short backoff
cap, optimized for a bounded worst case the user will tolerate. Batch =
more retries, longer timeout, longer backoff cap, optimized for eventual
success over raw latency, since nothing downstream is blocked waiting on
any one call.

## Part 5.IV - Agent Scenarios (local Ollama model)

Model: `qwen3:8b` via Ollama (thinking mode disabled with `think=False`;
`temperature=0`). `max_steps=5`. Tools: the real database-backed registry
through `execute_tool()`, with the Part 5.I safety rule active
(`search_recalls` limit > 25 is blocked). Tool results are compacted to the
first 3 records before being fed back to the model; the full results are
what is logged. Produced by `scripts/run_agent_scenarios_hw05.py`; the
step-by-step log is `reports/hw05/raw/agent_runs.jsonl`. That file holds two complete passes of
the four scenarios (2026-10-05 02:41 and 03:53, with identical step counts, stop reasons and tool-call
counts); the table below is the later pass (run ids `a4691446`, `fe5d1664`, `36e27e9a`, `cec69f1c`).

| Scenario | Step count | Stop reason | Tool-call count |
|---|---|---|---|
| search ("juice") | 2 | normal_completion | 1 |
| detail (record 15007) | 2 | normal_completion | 1 |
| multi-step (record 15007, then its source) | 3 | normal_completion | 2 |
| safety-rule trigger (limit 50) | 1 | safety_rule_block | 1 |

Notes:

- A first pass used IDs that don't exist in the seeded data (record 1,
  source 1, the word "milk"). All three of those runs ended
  `normal_completion` with a correct "not found" answer, so the loop worked,
  but they never exercised real tool results. That pass is kept as
  `reports/hw05/raw/agent_runs_first_pass_nonexistent_ids.jsonl`, and the
  table above comes from the second pass.
- The `max_steps` stop reason is not reached by any live run; it is covered
  by the offline `MockModel` test (a model that never finishes is stopped at
  exactly `max_steps`) in `scripts/test_execute_tool_hw05.py`.
