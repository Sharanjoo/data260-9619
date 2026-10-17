# HW6 Part 4 - results and comparison (SID4 9619)

## Files

- `AGENT.md` (final, 5 sections with 13 instruction lines, plus the earlier HW1 code-review rules), `MEMORY.md` (live memory used by the CLI demo).
- `reports/hw06/MEMORY_original.md` (55 lines) and `reports/hw06/MEMORY_consolidated.md` (38 lines, final run). Earlier runs: `reports/hw06/raw/run1/`, `raw/run2/`.
- Code: `src/file_memory.py` (loading both files, system prompt, last-consolidated timestamp, trigger, consolidation with checks, `/memory`, `/compact`, `/dream`, `/help`), `scripts/file_memory_cli.py`, `scripts/run_consolidation_hw06.py`, `scripts/check_agent_md_compliance_hw06.py`, `scripts/test_file_memory_hw06.py` (53 offline checks).

## Consolidation trigger

Consolidation is due when MEMORY.md has more than 40 non-empty, non-comment lines (headings and bullets count) or its `last-consolidated` stamp is older than 24 hours. The 55-line test file shows both reasons (52 memory lines; last consolidated 367 hours ago).

## /compact evidence (final run, qwen3:8b)

| | Memory lines | Facts | File lines |
|---|---:|---:|---:|
| Before | 52 | 50 | 55 |
| After | 35 | 28 | 38 |

18 duplicates merged, 3 older facts superseded, 1 fact flagged for review, 2 passes. In the CLI demo `/compact` on the 11-line live MEMORY.md changed nothing (3 proposed merges between unrelated lines were refused by the checks).

## Three consolidation runs, same input

| Run | Checks passed | Main problems |
|---|---:|---|
| 1 | 6 / 12 | unrelated lines merged away; `[critical]` allergy moved out of Facts |
| 2 | 6 / 12 | oat milk and MySQL facts lost by wrong merges; allergy pair left unresolved in Facts; daily/weekly flagged UNRESOLVED (both kept) |
| 3 (final) | 11 / 12 | daily/weekly digest treated as a duplicate (older line kept) |

Final run, contradictions: C1 San Jose to Oakland correct; C4 port 8000 to 8619 correct; C2 (the trap, a joking "not allergic" line newer than the doctor-confirmed `[critical]` allergy) correct only because the guard reversed the model's proposal, the joke line is logged as NEEDS REVIEW; C3 daily/weekly digest resolved incorrectly (the newer weekly line was merged into the older daily line, no conflict logged). Duplicates: all five groups reduced to one line each; all 19 unique facts survive.

## Does a generated function follow AGENT.md?

qwen3:8b (AGENT.md and MEMORY.md in its system prompt) wrote `normalize_notice_title` and tests four times, with the checker's failures fed back each time. Behaviour and tests were fine (rules 3 to 7 passed), but every attempt broke rule 1 (no return type hint on the test functions) and rule 2 (multi-line docstring), so it passed 5 of 7 rules. The reference implementation in `src/notice_text.py` with `tests/test_notice_text_hw06.py` passes 7 of 7, and a deliberately non-compliant sample fails the checker, so the checker does tell the two apart.

## MongoDB memory vs file memory

| | MongoDB memory (Parts 2 and 3) | File memory (AGENT.md + MEMORY.md) |
|---|---|---|
| Inspectability | Needs Compass or the `/api/memory` endpoint; embeddings are lists of floats nobody can read | Open the file in any editor; `git diff` shows exactly what a consolidation changed |
| Persistence after restart | Persists in the `mongo_data_s9619` Docker volume | Persists on disk; shown by the restart check (a new process remembered the allergy and the git preference) |
| Scalability across many sessions | Good: indexed by user and session, only the top 3 facts (about 9 tokens per turn in the sweep) enter the prompt | Poor: the whole file goes into every prompt (the 35-line consolidated file is about 3.4 KB, roughly 850 tokens per turn), and it needs periodic consolidation |
| Must-not-forget facts | Not guaranteed: facts are only retrieved when similar enough to the question (cosine at least 0.45, top 3); in the sweep, probe P5 retrieved no fact in any setting | Always in the prompt, can be tagged `[critical]`, and a person can review it; but an LLM consolidation can still damage it (run 3 lost the weekly preference), so it needs guards and review |

Conclusion: use a hybrid. Keep a short file of facts that must never be forgotten (allergies, standing rules) in MEMORY.md and load it every turn, and keep the large, growing conversation history in MongoDB, retrieved by similarity. Any LLM that rewrites the file needs checks around it, and the result needs a human look.
