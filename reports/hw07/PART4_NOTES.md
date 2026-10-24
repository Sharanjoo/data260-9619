# HW7 Part 4 — Bay Wheels Membership-vs-Pay-Per-Use Agent

Sharan Lourduraj, SID4 9619. Model: `qwen3:8b` (Ollama, local, CPU, single-threaded).
Pricing source for every run below: `https://www.lyft.com/bikes/bay-wheels/pricing`.
All figures in this file are taken directly from `reports/hw07/RUN_LOG.txt` and the saved
`reports/hw07/raw/bike_run_<label>.json` / `reports/hw07/raw/bike_snapshots/` files. Nothing here
is rounded to make a wrong number look closer to correct.

---

## About the data (read this first)

Both scenario files are built by `scripts/build_bike_scenarios_hw07.py` (seed 9619) from one real month of Bay Wheels trips (October 2024, `202410-baywheels-tripdata.csv.zip`, 378,317 rows). Summary: `reports/hw07/raw/bike_trip_data_summary.json`.

- **Scenario M (540 trips):** real trips by Bay Wheels members that started in October 2024 (real timestamps, one calendar month, a heavy-user profile: 414 ebike and 126 classic rides).
- **Scenario P (504 trips): the dates are SYNTHETIC.** The 504 trips are real short (15 minutes or less) classic-bike trips by casual riders, but each trip's start date was replaced so that there are exactly 7 trips in each of the 72 months from 2019-01 to 2024-12 (an occasional rider). Time of day and ride duration are the real values; the original timestamp is kept in the `orig_started_at` column. The file and this note say so on purpose; the 72 "calendar months" in the results below come from this remapping, not from a real six-year rider.
- The trips are from 2024, but they are priced with the pricing page fetched on 2026-10-23 and 2026-10-24, so the dollar totals are illustrative, not a statement of what these riders actually paid.
- The reference calculation (`src/bike_pricing.py`) assumes exact fractional minutes and buys the monthly pass for every calendar month that has at least one trip.


## Scenario M (membership should win)

**Final run used: `M_run4`** (started 2026-10-23T05:14:25Z, ended 2026-10-23T05:29:00Z)

| | Agent | Independent reference |
|---|---|---|
| Decision | Buy Monthly Membership | Buy Monthly Membership |
| Pay-per-use total | $2,497.45 | $2,911.45 |
| Membership total | $803.25 | $805.58 |
| Break-even (rides/month) | 115 | 7.3 |
| Actual rides/month | 540 | 540 |

Automatic checks (from `bike_run_M_run4.json["checks"]`):
- [PASS] decision matches reference
- [FAIL] pay-per-use total within 2% (agent is $414.00 low, i.e. 14.2% under the reference total)
- [PASS] membership total within 2% (agent is $2.33 low, i.e. 0.29% under)
- [PASS] finished with a final answer
- [PASS] pricing page was fetched
- [PASS] snapshot still supports the reference prices

Run mechanics: stop reason `final_answer`, 7 tool-call steps, 866.6 s wall time, 23,903 input + 860
output tokens. Pricing page accessed 2026-10-23T05:16:49Z, SHA-256
`7d7d2b214669846cda0dc947705d57072ed533434a7e678375d8434ac9148d13` (4,761 chars).

The pay-per-use SQL the model wrote (`...ELSE 1.00 + 0.19 * duration_min...`) only adds the $1.00
unlock fee on the `ELSE` branch, i.e. to classic-bike rides; electric-bike rides (414 of the 540
rides in this scenario) get no unlock fee at all, which is why the agent's pay-per-use total comes
in $414 below the reference. The membership total happens to land within 2% anyway. The decision
itself is correct only because membership is so much cheaper here that even a $414 understatement
of the losing option doesn't flip the comparison; the break-even figure the agent reports (115
rides/month) is 15.8x the reference figure (7.3), so that intermediate number is wrong even though
the final decision is right.

### Earlier attempts (scenario M), oldest first

- **M_attempt1** (unlabeled, started 2026-10-23T01:44:14Z): stopped after step 5 with no stop
  reason, no final answer, and no `END exit_code=` line in RUN_LOG — the run was interrupted
  before `run_bike_agent_hw07.py` exited normally. No raw JSON was saved under this attempt.
- **M_attempt2** (unlabeled, started 2026-10-23T03:31:28Z): stop reason `max_steps`, 15 steps,
  1037.4 s, 51,495+873 tokens. From step 10 onward the model re-issued the identical `csv_sql`
  query six times in a row and never produced a final answer (decision: none). Checks: decision
  FAIL, pay-per-use FAIL, membership FAIL, finished-with-final-answer FAIL, pricing-fetched PASS,
  snapshot PASS (2/6). Saved to `bike_run_scenario_M.json` (later overwritten by M_attempt3).
- **M_attempt3** (unlabeled, started 2026-10-23T03:51:33Z): stop reason `final_answer`, 9 steps,
  1091.7 s, 32,159+1,048 tokens. Decision correct (Buy Monthly Membership) but both totals were
  badly off: pay-per-use $5,104.05 vs reference $2,911.45 (75.3% high), membership $74.71 vs
  reference $805.58 (90.7% low — the model's per-minute-charge query undercounted by roughly a
  factor of 17). Checks: decision PASS, pay-per-use FAIL, membership FAIL, finished PASS, fetched
  PASS, snapshot PASS (4/6). Saved to `bike_run_scenario_M.json`, overwriting M_attempt2's file.
- **M_run3** (started 2026-10-23T04:20:05Z): stop reason `final_answer`, 7 steps, 921.7 s,
  23,768+866 tokens. Decision correct. Pay-per-use $2,371.45 vs reference $2,911.45 (18.5% low —
  same classic-only-unlock-fee bug as M_run4, slightly worse). Membership $805.58, an exact match
  to the reference. Break-even 12 vs reference 7.3. Checks: decision PASS, pay-per-use FAIL,
  membership PASS, finished PASS, fetched PASS, snapshot PASS (4/6). Saved to
  `bike_run_M_run3.json`.
- **M_run4**: see above — the run used for the summary table. Same 4/6 check pattern as M_run3.

---

## Scenario P (pay-per-use should win)

**Final run used: `P_run4`** (second start 2026-10-23T06:23:32Z, ended 2026-10-23T06:37:28Z — see
note on the false start below)

| | Agent | Independent reference |
|---|---|---|
| Decision | Buy Monthly Membership | **Pay Per Ride/Minute** |
| Pay-per-use total | $1,332.22 | $1,332.22 |
| Membership total | $2,088.00 | $2,088.00 |
| Break-even (rides/month) | 72 | 11.0 |
| Actual rides/month | 72 | 7.0 |

Automatic checks (from `bike_run_P_run4.json["checks"]`):
- [FAIL] decision matches reference
- [PASS] pay-per-use total within 2% (exact match)
- [PASS] membership total within 2% (exact match)
- [PASS] finished with a final answer
- [PASS] pricing page was fetched
- [PASS] snapshot still supports the reference prices

Run mechanics: stop reason `final_answer`, 9 tool-call steps, 828.9 s wall time, 32,040 input + 795
output tokens. Pricing page accessed 2026-10-23T06:24:36Z, SHA-256
`7d7d2b214669846cda0dc947705d57072ed533434a7e678375d8434ac9148d13` (4,761 chars) — the identical
hash seen on every M and P run in this file, so the pricing page content did not change across the
whole Part 4 test session.

Both dollar totals are exact matches to the independent reference, which makes this the agent's
most numerically accurate run of either scenario — and it still gets the decision wrong. The
agent's own final text states PAY-PER-USE TOTAL $1,332.22 and MEMBERSHIP TOTAL $2,088.00, i.e. its
own numbers say pay-per-use is $755.78 cheaper, yet its DECISION line says "Buy Monthly
Membership." This is not a rounding issue or a borderline call; the stated decision directly
contradicts the two numbers stated immediately below it in the same answer. The agent also
reused the `COUNT(DISTINCT ride_month)` value (72, an artifact of this scenario's trip log spanning
72 sparse calendar months) as both its break-even figure and its actual-rides-per-month figure;
the correct actual rate is 504 rides / 72 months ≈ 7.0 rides/month, which is what the reference
uses. Separately, the model's own WEEKLY TABLE line in the final answer lists the header only with
no rows, even though the step-9 `csv_sql` call it had just run returned 6 rows of weekly data.
The weekly table in the scenario-M run above was reproduced correctly, so this drop is specific to
this run.

**Note on the P_run4 label:** RUN_LOG shows two `START` entries for `--label P_run4`. The first
(2026-10-23T06:20:14Z) logged only the startup banner and the "uploaded trips" line, then stopped
with no further steps and no `END exit_code=` line — it was interrupted immediately after upload,
before issuing any tool call. The second start (2026-10-23T06:23:32Z) is the one that ran all 9
steps to completion and is the run saved to `bike_run_P_run4.json` and reported above.

### Earlier attempts (scenario P), oldest first

- **P_run1** (started 2026-10-23T04:38:35Z): stop reason `max_steps`, 15 steps, 862.2 s,
  56,274+678 tokens. From step 3 through step 15 the model re-issued the exact same
  `SELECT rideable_type, COUNT(*)...` query 13 times in a row and never progressed past it; no
  final answer, decision: none. Checks: decision FAIL, pay-per-use FAIL, membership FAIL,
  finished FAIL, pricing-fetched PASS, snapshot PASS (2/6).
- **P_run2** (started 2026-10-23T04:56:14Z): stop reason `final_answer`, 9 steps, 922.4 s,
  32,062+978 tokens. Decision: Buy Monthly Membership (reference: Pay Per Ride/Minute) — FAIL, and
  the same self-contradiction seen in P_run4: its own final text gives PAY-PER-USE TOTAL $1,332.22
  and MEMBERSHIP TOTAL $2,016.00, i.e. pay-per-use is cheaper by its own numbers, yet it decided
  membership. Pay-per-use $1,332.22 matched the reference exactly (PASS). Membership $2,016.00 vs
  reference $2,088.00 (3.5% low — the model spread the $29 monthly fee across rides via
  `29 * 72 / 504` per row instead of charging it once per month as the reference does). Checks:
  decision FAIL, pay-per-use PASS, membership FAIL, finished PASS, fetched PASS, snapshot PASS
  (4/6).
- **P_run3** (started 2026-10-23T05:29:01Z): stop reason `model_error` at step 9 — the Ollama
  server dropped the connection mid-generation
  (`RemoteProtocolError: peer closed connection without sending complete message body (incomplete
  chunked read)`) — after 2,579.1 s (~43 minutes), far longer than any other run in this file, and
  with no final answer (decision: none). Checks: decision FAIL, pay-per-use FAIL, membership FAIL,
  finished FAIL, pricing-fetched PASS, snapshot PASS (2/6). This is the stalled run that made the
  P_run4 re-run necessary.
- **P_run4**: see above (counting only the completed second start) — the run used for the summary
  table, and the best-scoring P attempt (5/6 checks), with decision as the one remaining failure.

---

## Pattern across both scenarios

Across the two scenarios, every P run that reached a final answer (P_run2, P_run4) stated a
"Buy Monthly Membership" decision that contradicted its own stated pay-per-use/membership totals
(pay-per-use was the cheaper number both times). No M run showed the equivalent error in the other
direction — all three M runs that reached a final answer (M_attempt3, M_run3, M_run4) correctly
said "Buy Monthly Membership," which also happens to be the textually identical phrase the model
defaults to. Whether this is a genuine inability to compare its own two numbers or a fixed
preference for recommending membership regardless of the numbers is not something these six runs
can distinguish, since every M scenario's correct answer happens to also be "Buy Monthly
Membership" — but the P-scenario runs show the agent computing the right numbers and then stating
a conclusion those numbers do not support.

---

## UI runs (Streamlit page `bike_ui/bike_app.py`, port 8620, defences on)

These two runs were made through the page itself for the UI screenshots (CSV chosen with the demo-scenario dropdown, pricing URL left at the default). The page does not write a raw JSON file, so the numbers below are read from the page; the same pricing page was fetched (SHA-256 `7d7d2b21...9148d13`).
The first M run through the page showed `$...$` amounts rendered as maths and a collapsed timeline; the page was fixed (plain-text answer, escaped dollar signs, timeline kept open) and scenario M was run again. Only the fixed-page runs are used for the screenshots.

| | Scenario M (UI run) | Scenario P (UI run) |
|---|---|---|
| Agent decision | Buy Monthly Membership (correct) | Buy Monthly Membership (WRONG; reference: Pay Per Ride/Minute) |
| Pay-per-use total (agent / reference) | $2,371.45 / $2,911.45 (wrong by $540: no unlock fee) | $1,332.22 / $1,332.22 (exact) |
| Membership total (agent / reference) | $805.58 / $805.58 (exact) | $2,088.00 / $2,088.00 (exact) |
| Break-even rides per month (agent / reference) | 1565.87 / 7.3 (wrong) | 13.0 / 11.0 (wrong); "actual" 504.0 vs reference 7.0 |
| Steps, time, stop reason | 9, 963.6 s, final_answer | 9, 982.0 s, final_answer |
| Tokens in / out | 31,689 / 1,004 | 32,372 / 823 |
| Page warning | none | "decision does not match its own totals" shown |

Scenario P: the page's check message fired because the agent's own two totals (pay-per-use $1,332.22 < membership $2,088.00) say pay-per-use is cheaper while its decision says membership, the same self-contradiction seen in P_run2 and P_run4. The page reports it; it does not change the agent's answer.
