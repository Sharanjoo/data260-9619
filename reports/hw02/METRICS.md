# Homework 2 – Metrics

## Configuration
- SID4: 9619
- PORT_BASE: 8619
- PREFIX: s9619
- SEED: 9619
- VERIFY_SEED: 269619
- DOMAIN_ID: 3 (Grocery Supply and Recall Notices)
- Local model: qwen3:8b (Ollama)

## Part 4 #3 Schema-validation classification (30 runs, fixed input, turn ceiling = 10)

Fixed input: `reports/hw02/cases/schema_input.json` ("Milano Cookies Allergen Alert")

| Outcome over 30 runs      | Count | Mean latency (ms) |
| -------------------------- | ----: | -----------------: |
| Valid first attempt         |    30 |           26793.518 |
| Valid after 1 retry         |     0 |                   — |
| Valid after 2+ retries      |     0 |                   — |
| Hit turn ceiling            |     0 |                   — |

**Interpretation:** On this fixed input, `qwen3:8b` produced a schema-valid, Reviewer-approved proposal on the first Planner attempt in all 30 runs. No retries of any kind were needed. This indicates the model is highly reliable for single-issue, clearly worded recall notices.

## Part 4 #4 Turn-ceiling comparison (2 vs 10, 20 runs each, same fixed input)

| Turn ceiling | Completion rate | Mean latency (ms) | n  |
| ------------ | ---------------: | -----------------: | -: |
| 2            |             1.00 |           28626.236 | 20 |
| 10           |             1.00 |           26373.833 | 20 |

**Interpretation:** Both ceilings achieved 100% completion with comparable latency (the ~2.2s difference is within normal run-to-run variance, not caused by retries none occurred at either ceiling on this input). Since raising the ceiling from 2 to 10 produced no reliability gain on this input, **ceiling = 2 is chosen for deployment**: it achieves identical reliability while bounding worst-case latency/cost more tightly for harder inputs.

## Part 4 #5 Adversarial input (5 runs, turn ceiling = 2)

Adversarial input: `reports/hw02/cases/adversarial_input.json` a single notice bundling four unrelated incidents across four facilities.

**Result: 5/5 runs (100%) hit the turn ceiling** every run's proposal was rejected by the Reviewer on the first attempt, and with ceiling = 2 there was no room left to retry.

Representative Reviewer rejection reasons observed across the 5 runs:
- "The tags 'product recall' and 'labeling error' are not distinct enough and the 'food safety incident' tag is too generic. The summary is accurate but exceeds 25 words."
- "The tags 'food safety recall' and 'quality control issues' are not distinct enough... 'quality control issues' overlaps with 'food safety recall'."
- "'Labeling Errors' is a subset of 'Quality Control Issues', and the summary is inaccurate and exceeds 25 words."
- "'Labeling Errors' is specific but not fully supported by the content, as the labeling error is only one of four incidents."

**Why this input causes trouble:** the notice bundles four unrelated incidents into one notice, but the schema only allows exactly 3 tags and a summary of at most 25 words. The Planner cannot satisfy both constraints at once: generalizing tags to cover multiple incidents produces overlapping, "not distinct enough" tags; naming all four incidents blows past the 25-word cap; and picking a tag grounded in only one incident gets flagged as incomplete. This is a structural mismatch between the fixed output shape and the input's inherent complexity, not a stochastic sampling issue all 5 runs failed for the same category of reason.

**Proposed fix:** since retries alone don't address a structural mismatch, a higher turn ceiling would not reliably fix this case. The better fix is upstream: detect when a notice bundles multiple unrelated incidents and route each incident through its own single-issue tagging pass, rather than forcing one Planner call to compress all of them into 3 tags and 25 words.

## Part 3 — Self-correction loop verification

With `--force-reviewer-issue` and `--turn-ceiling 6`, the graph correctly looped Planner → Reviewer (rejected) → Planner → Reviewer (rejected) twice before stopping at the turn ceiling, confirming both the correction loop and the safety cutoff work as designed.

With `--force-planner-invalid-once`, the first Planner attempt was deliberately corrupted to 2 tags, causing a real Pydantic `ValidationError`; the graph correctly fed that error back to the Planner, which then produced a valid, Reviewer-approved proposal on the second attempt.