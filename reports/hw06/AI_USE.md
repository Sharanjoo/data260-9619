# AI_USE.md HW6 (SID4 9619)

## 1. What I used an AI assistant for, and what I did myself

I used an AI assistant to revise the HW6 code and write-ups: the token and latency logging, the 30-message sweep runner and the METRICS builder (Part 3), the file-based memory module with `/memory`, `/compact` and `/dream`, the consolidation checker and the `make verify-hw06` script (Part 4), and drafts of METRICS.md, this file and the Part 4 comparison.

What I did myself: Execution of Docker, MongoDB and Ollama, ran every script on my laptop (the model is qwen3:8b on CPU, so the full sweep took hours), reviewed the real output, asked for fixes when a run was wrong, re-ran after each fix, and checked that the results satisfy the HW6 requirements.

## 2. One AI-produced output that was wrong or unsuitable

The local model, qwen3:8b, was asked to consolidate a 55-line MEMORY.md (50 facts with duplicates and deliberate contradictions), and its decisions were wrong in several ways. The first version of the assistant's code trusted those decisions too much.

- Run 1 (6 of 12 checks passed): the model merged unrelated lines into each other (six unique facts disappeared from the Facts section: the student name, PREFIX, VERIFY_SEED, the repository URL, the collaborators and the laptop) and it flagged both peanut-allergy lines against each other, so the doctor-confirmed `[critical]` allergy was moved out of the Facts section.
- Run 2 (6 of 12): after the first fixes, two facts were still lost by wrong merges: "toddler drinks oat milk" was merged into "partner is lactose intolerant" and the MySQL line was merged into the "chat model" line.
- Run 3 (11 of 12): the last failure is a contradiction resolved the wrong way round. The model treated "wants a daily email digest" and "wants a weekly email digest" as duplicates and kept the older daily line, so the newer weekly preference was dropped (only an inline "merged duplicates" note remains).

Separately, the function that qwen3:8b generated under AGENT.md broke two rules (type hints on every function, one-line docstrings) on all four attempts, even though the checker's failure messages were fed back each time (5 of 7 rules passed every time).

## 3. How it was detected

Before the first consolidation run I wrote the ground truth in `reports/hw06/consolidation_truth.yaml` (which lines are duplicates, which pairs contradict each other, and which 19 facts must survive) and an evaluator, `scripts/run_consolidation_hw06.py`, that checks the result against it. The real runs showed the failed checks, and I read the "Resolved conflicts" section and the warnings by eye as well. For the AGENT.md test, `scripts/check_agent_md_compliance_hw06.py` checks the generated code with an AST parser plus tests and reports each rule as pass or fail. In Part 3 the first N=4 sweep was caught from the real run output: every probe request returned HTTP 422 because the running container still had an outdated image, so the sweep was stopped and that attempt discarded.

## 4. What changed, and why it works now

The code now treats the model only as a proposer. A decision is ignored (and the fact is kept) when the two lines share fewer than two content words, when the line number and the quoted words point at different facts, when an older line would replace a newer one, or when a proposed merge joins two lines that overlap too little to be duplicates. A `[critical]` fact can never leave the Facts section through supersede or review, and if the model flags both lines of a pair against each other, both stay in Facts with one UNRESOLVED entry in "Resolved conflicts". The offline tests grew from 43 to 53 and reproduce each failure that the real model produced. I kept the earlier results (`reports/hw06/raw/run1/`, `reports/hw06/raw/run2/`) and the full console output in RUN_LOG.txt instead of deleting them.

What is still wrong: the daily/weekly contradiction (C3) is still resolved incorrectly in the final run, because the two lines look almost identical to simple checks, and I report it as it happened instead of tuning more. `make verify-hw06` therefore checks hard safety rules (under 40 lines, nothing silently deleted, the critical allergy still in Facts) and records the model's decision quality as information instead of passing or failing on it. Other fixes found by running things for real: the memory extractor invented facts from questions (for example "User has a food allergy"), so the extraction prompt now forbids facts from questions or hypotheticals; and a Windows console crash on an emoji in a model reply stopped the sweep on its last probe, so the scripts now print UTF-8 and the sweep resumed from its saved progress.
