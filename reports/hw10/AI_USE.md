# HW10 AI Use

Sharan Lourduraj, SID4 9619

## 1. What did you use AI for, and what did you do yourself?

I used Claude for code assistance the DeepEval judge wrapper and GEval rubrics, the Kafka collector and evaluator, the latency and judge-validation scripts and their tests and the report text. I ran every command on my own computer, started Docker, Kafka, Redis, Ollama and the three agents, pasted the outputs back, ran all git commands, and took the screenshots. I wrote the 20 labels and their notes myself, from the labeling rubric, before any judge score existed, and committed them (6861ada) before the first judge run. I also made the calls on how to produce the failed trace, when to stop the latency run, and what to say about trusting the judge.

## 2. Describe one thing the AI got wrong, or one thing you verified.

The question list the assistant wrote for the 50-miss latency run could not reach 50 misses. Several questions asked about the same recall record in different words, and the semantic cache scored them 0.977 to 0.992 against each other, so they were answered from the cache. The run correctly excluded them, but the pool of 77 questions would have run short, so 36 general questions were added. I also started a second copy of the latency script by mistake. The assistant noticed from the log that questions 20 to 30 appeared twice and that latencies had jumped from about 60 to 110 s to 150 to 190 s, and had me stop both. The overlapped rows were moved aside (not deleted) and the run resumed on one copy. Earlier in the work, the assistant's own hand-computed expected values in a test of the statistics (mean absolute difference, Spearman) were wrong; scipy gave the right ones, and the tests were corrected to match it, not the other way round.

## 3. How did you verify AI output?

Every code step had offline tests before it ran on the real system (28 tracing, 22 evaluator, 10 latency, 19 judge-validation, 26 dashboard tests, plus the HW8 and HW9 suites, all re-run by `make verify-hw10`). The verification script recomputes the percentile table, Spearman, mean absolute difference and repeatability from the raw per-request and per-case rows instead of trusting the saved summaries, and checks that the label commit is older than the first judge score. The judge refuses to run unless the labels are committed and unedited. I looked at the raw judge reasons, which showed it scoring identical draft and final text differently. I checked the span timings against the Writer's own console log (three failures at 04:09:41, 04:09:44 and 04:09:46 matched the three `writer` error spans).

## 4. What changed because of the AI, and what are the limits?

The assistant produced code and wording faster than I could, but the conclusions that matter come from the data and my labels: the judge gave a 4 to all three drafts I scored 1, 1 and 2, so I would not use it as a deployment gate. Limits: 20 cases labeled by one person; the judge and the Writer are the same model (qwen3:8b), so the judge may favor the Writer's style; the judge scores are perfectly repeatable only because temperature is 0; the latency run sent one request at a time, so it says nothing about concurrent load; the Reviewer returned every draft unchanged, so Final-vs-Draft is 0 by design and the non-zero judge differences are noise; and the latency run was interrupted once and restarted (disclosed in METRICS.md). AI wrote the report text; I read it against the raw files before submitting.
