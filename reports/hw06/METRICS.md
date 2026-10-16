# HW6 METRICS - what memory costs

Student: Sharan Lourduraj (SID4 9619, PORT_BASE 8619, PREFIX s9619, SEED 9619, VERIFY_SEED 269619, DOMAIN_ID 3 - grocery recall notices).  
Model: qwen3:8b via Ollama on CPU only (HP Pavilion, 32 GB RAM, no GPU); embeddings: nomic-embed-text; MongoDB 7 database `s9619_doc`.  
Memory settings during the sweep: summary every 5 user messages, lifetime summary after 2 session summaries, episodic top-k 3 with minimum cosine 0.45. Server source fingerprint 6b3fc415295cc617 (equals the repository fingerprint, so the running container matched the committed code).

## How the numbers were measured

- **Tokens** are Ollama's own counts for each `/api/chat` call: `prompt_tokens` = `prompt_eval_count`, `completion_tokens` = `eval_count` of the answer call. The memory machinery makes extra model calls (fact extraction every message, a session summary every 5 user messages, a lifetime summary occasionally); those are logged separately as *overhead* tokens and are included in the cost estimate but not in the prompt-size columns.
- **Tokens by component** (system primer / long-term summary / short-term window / episodic facts / current message) are character-count estimates (chars / 4) scaled so that the five parts add up to the real `prompt_tokens`. Ollama only reports a total, so the split is an estimate; the total is exact.
- **Latency**: `reply latency` is the time of the answering model call; `total latency` is the whole `/api/chat` request (answer + fact extraction + summaries + embeddings). The brief asks for mean latency, so the main table shows the total in ms and the reply-only value next to it.
- **Conversation**: the same 30 user messages (`conversation_30.yaml`) in a fresh user and session for each setting. A window of N counts stored *messages* (user and assistant), so N=30 holds the last 15 turns. The five probes were asked after message 30 in `read_only` mode (they are answered with memory but not stored, so they do not change the memory being tested).
- **Probe scoring** is rule based, from `memory_probes.yaml` (written before testing): 5 = every required fact present and no stale fact, 4 = required present but stale fact also mentioned, 3 = at least half of the required facts, 2 = wrong but confident, 1 = says it does not know or only the stale fact.

## Part 2 - the 12-message memory demo

| Message | Prompt tokens | Completion tokens | Short-term messages | Episodic facts used | Summary updated | Total latency (s) |
|---:|---:|---:|---:|---:|:---:|---:|
| 1 | 105 | 43 | 1 | 0 | - | 84.1 |
| 2 | 173 | 35 | 3 | 0 | - | 31.2 |
| 3 | 227 | 45 | 5 | 0 | - | 26.7 |
| 4 | 296 | 47 | 7 | 0 | - | 35.8 |
| 5 | 364 | 36 | 9 | 0 | session | 109.2 |
| 6 | 549 | 73 | 11 | 0 | - | 82.8 |
| 7 | 615 | 39 | 12 | 0 | - | 71.9 |
| 8 | 624 | 45 | 12 | 2 | - | 60.0 |
| 9 | 650 | 46 | 12 | 3 | - | 68.3 |
| 10 | 646 | 31 | 12 | 3 | session | 159.1 |
| 11 | 637 | 24 | 12 | 3 | - | 78.8 |
| 12 | 592 | 81 | 12 | 0 | - | 68.6 |

Prompt size grows while the window fills (messages 1-7) and then levels off at about 600-650 tokens because the window is capped at 12 messages; the full conversation and the three memory collections are in the screenshots.

## Part 3 - SHORT_TERM_N sweep and the compression policy

### Main table (30 messages per setting, mean per message)

| Setting | Mean prompt tokens / turn | Mean latency (ms), total request | Mean reply latency (ms) | Probe quality (1-5) |
|---|---:|---:|---:|---:|
| SHORT_TERM_N=4 | 473.5 | 41,764 | 21,698 | 5.0 |
| SHORT_TERM_N=12 | 793.6 | 63,739 | 42,035 | 5.0 |
| SHORT_TERM_N=30 | 1,164.8 | 74,713 | 55,784 | 5.0 |
| SHORT_TERM_N=30 + compress_old_assistant | 829.7 | 54,925 | 35,940 | 5.0 |

Extra detail (not required by the brief):

| Setting | Mean completion tokens / turn | Mean overhead prompt tokens / turn | Mean overhead completion tokens / turn | Peak prompt tokens | Median reply latency (ms) |
|---|---:|---:|---:|---:|---:|
| SHORT_TERM_N=4 | 50.2 | 422.8 | 55.4 | 637 | 20,117 |
| SHORT_TERM_N=12 | 59.7 | 438.3 | 61.3 | 1,125 | 45,415 |
| SHORT_TERM_N=30 | 52.8 | 424.7 | 56.7 | 1,713 | 73,586 |
| SHORT_TERM_N=30 + compress_old_assistant | 45.5 | 420.5 | 55.7 | 1,129 | 44,459 |

### Where the prompt tokens go (mean per turn, estimated split scaled to the real total)

| Setting | System primer | Long-term summaries | Short-term window | Episodic facts | Current message | Total |
|---|---:|---:|---:|---:|---:|---:|
| SHORT_TERM_N=4 | 69 | 269 | 115 | 8 | 12 | 474 |
| SHORT_TERM_N=12 | 72 | 291 | 410 | 9 | 12 | 794 |
| SHORT_TERM_N=30 | 73 | 273 | 798 | 9 | 13 | 1165 |
| SHORT_TERM_N=30 + compress_old_assistant | 77 | 298 | 431 | 10 | 13 | 830 |

The primer and the current message are almost constant. The short-term window is the part that grows with N, and it is the only part the compression policy shrinks.

### Probe scores

| Probe | Question | N=4 | N=12 | N=30 | N=30 + compress_old_assistant |
|---|---|---:|---:|---:|---:|
| P1 | What food allergy do I have? | 5 | 5 | 5 | 5 |
| P2 | Which two grocery stores do I shop at? | 5 | 5 | 5 | 5 |
| P3 | What does my toddler drink every day? | 5 | 5 | 5 | 5 |
| P4 | Which city do I live in now? | 5 | 5 | 5 | 5 |
| P5 | What kind of updates did I ask you to send me, and how often? | 5 | 5 | 5 | 5 |
| **Mean** | | **5.0** | **5.0** | **5.0** | **5.0** |

Probe facts were planted so that the earliest ones (messages 1 and 2) fall outside every window, one only fits N=30, one fits N=12 and N=30, and one fits all. Every setting still answered all five correctly. The retrieved-fact column of `part3_probes.csv` shows where the answers could come from: N=4: no episodic fact retrieved for P5; N=12: no episodic fact retrieved for P5; N=30: no episodic fact retrieved for P5; N=30 + compress_old_assistant: no episodic fact retrieved for P5. Probes with a retrieved fact were answered from the episodic store; a probe without one can only have been answered from the session/lifetime summaries or the window.

### Compression policy (`compress_old_assistant`): token savings and quality change

Policy: keep the last 2 history messages verbatim, cut every older assistant reply to its first sentence (at most 120 characters); user messages are never touched. Window size stays 30.

| Comparison | N=30 without policy | N=30 with policy | Change |
|---|---:|---:|---:|
| Mean prompt tokens / turn | 1,164.8 | 829.7 | -335.1 tokens (-28.8%) |
| Mean short-term window tokens / turn | 797.6 | 431.3 | -45.9% |
| Mean probe quality | 5.0 | 5.0 | +0.0 |
| Mean total latency (ms) | 74,713 | 54,925 | -19,788 ms |

The policy cut prompt size by about 29% with no measurable change in probe quality on this conversation. Compared with N=12 (793.6 tokens), the policy keeps a 30-message window at a similar token cost (829.7 tokens), because the dropped text is the long assistant replies, not the user's facts.

## Cost estimate: 10,000 conversations of 30 turns

Price: $1.00 per 1M input tokens, $5.00 per 1M output tokens. Per conversation: input = sum over the 30 turns of (answer prompt tokens + overhead prompt tokens), output = sum of (answer completion tokens + overhead completion tokens). The five evaluation probes are not counted because they are not part of normal use. Total = per-conversation tokens x 10,000. Nothing was run on a paid hosted model; the tokens are the real counts from the local model.

| Setting | Input tokens / conversation | Output tokens / conversation | Cost / conversation | Cost for 10,000 conversations | Probe quality | Role |
|---|---:|---:|---:|---:|---:|---|
| SHORT_TERM_N=4 | 26,888 | 3,167 | $0.0427 | $427.23 | 5.0 | **best** |
| SHORT_TERM_N=12 | 36,958 | 3,631 | $0.0551 | $551.13 | 5.0 |  |
| SHORT_TERM_N=30 | 47,684 | 3,286 | $0.0641 | $641.14 | 5.0 | **worst** |
| SHORT_TERM_N=30 + compress_old_assistant | 37,507 | 3,035 | $0.0527 | $526.82 | 5.0 |  |

**How best and worst were chosen.** Worst = the most expensive setting (SHORT_TERM_N=30). Best = the cheapest setting whose probe quality is within 0.5 points of the highest quality seen (5.0), so that cheapness cannot win by forgetting facts. Here every setting scored 5.0, so best is simply the cheapest (SHORT_TERM_N=4). Choosing worst by cost alone is deliberate: it is the setting someone would pay for by default if they simply kept the longest history. Best saves $213.91 per 10,000 conversations ($0.0214 per conversation, 33.4% of the worst).

The memory overhead (extra extraction and summary calls) is about 438 input tokens per turn in every setting, which is 47% of all input tokens at N=4 but 27% at N=30; cheap windows therefore save less than the prompt-size column alone suggests.

## Interpretation and limits

- **Quality saturated.** All settings scored 5.0, so the probes cannot separate them. With episodic retrieval and summaries present, a window of 4 messages was enough for this 30-message conversation. This does not show that the window never matters: the probes are fact-recall questions, and a window-only agent (no summaries or episodes) was not tested here.
- **Cost scales with the window; quality did not.** Mean prompt size rose from 474 to 794 to 1,165 tokens as N grew 4 -> 12 -> 30, and latency followed the same order for the answer call.
- **Latency is noisy.** The runs were CPU-only on a laptop, one after another, and other load on the machine was not controlled, so total latency differs between runs by more than prompt size explains (for example the policy run, with prompt sizes close to N=12, was faster than N=12). Prompt tokens are exact and repeatable; latency should be read as indicative only. Latency spikes every 5th turn come from the session-summary call.
- **One conversation per setting, temperature 0.** There is no repeat to give a confidence interval; the numbers describe this one 30-message conversation.
- The rule-based scorer checks facts, not tone; the replies are stored in `part3_probes.csv` and were also read by hand.

## Raw files

`reports/hw06/raw/part3_turns.csv` (120 rows, one per message), `part3_probes.csv` (20 rows), `part3_probe_scores.json`, `part3_run_config.json`, `part3_summary.json` (all numbers above), `part2_chat_turns.json`, `part2_memory.json`, `part2_aggregate.json`; console output of the runs is in `reports/hw06/RUN_LOG.txt` (it also contains earlier aborted attempts: a first N=4 run that failed because the container held an outdated image, and a start-up timing failure; and the last N=30 run, which crashed on printing an emoji after storing its result and was resumed).

