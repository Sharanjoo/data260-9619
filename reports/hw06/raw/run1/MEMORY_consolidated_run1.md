# MEMORY.md
<!-- last-consolidated: 2026-10-16T06:53:13Z -->
<!-- format: one fact per bullet '- [YYYY-MM-DD] text'; tag [critical] for safety facts -->
## Facts
- [2026-08-27] Never run git commands yourself, hand them to the user.
- [2026-09-01] Report font is Times New Roman, tables have green headers. <!-- merged duplicates L9, L31, L43 -->
- [2026-09-02] Every terminal screenshot must show the name Sharan Lourduraj. <!-- merged duplicates L1, L10, L32, L47 -->
- [2026-09-03] Model: qwen3:8b (Ollama, local, no paid API). <!-- merged duplicates L2, L3, L5, L8, L13, L33, L45 -->
- [2026-09-04] The MongoDB database is s9619_doc, running as mongo:7.0 in Docker on host port 27017.
- [2026-09-05] The memory collections are messages, summaries and episodes.
- [2026-09-06] Episodic memory embeddings use nomic-embed-text served by Ollama.
- [2026-09-07] Domain: grocery recalls, DOMAIN_ID 3. <!-- merged duplicates L4, L15, L36, L48 -->
- [2026-09-08] SHORT_TERM_N defaults to 12 and a session summary is written every 5 user messages.
- [2026-09-09] The user runs all git commands (add, commit, push); the assistant only writes them out. <!-- merged duplicates L6, L38 -->
- [2026-09-10] The Part 1 collection is recall_notices with a status enum and a category enum.
- [2026-09-12] One FastAPI app serves every homework; MySQL holds the HW4 and HW5 relational data.
- [2026-09-14] In Postman, decline the AI Fix suggestion because it rewrites test bodies.
- [2026-09-19] The HW5 submission is tagged hw5 at commit 69fc4b5.
- [2026-09-23] Reports are exported as PDF named Lourduraj_HWn.pdf.
- [2026-09-26] The user prefers short answers.
- [2026-09-28] The user's toddler drinks oat milk every day.
- [2026-09-29] The user's partner is lactose intolerant.
- [2026-09-30] The user shops at Safeway and Whole Foods.
- [2026-10-01] The user wants a weekly email digest of recalls. <!-- merged duplicates L14 -->
- [2026-10-02] The API runs on port 8619 (PORT_BASE). <!-- merged duplicates L17 -->

## Resolved conflicts
- KEPT [2026-08-27] Never run git commands yourself, hand them to the user. | SUPERSEDED [2026-08-13] The assistant never runs git commands; the user runs them. | reason: Contradicted by newer line
- NEEDS REVIEW (kept: [2026-10-05] The user lives in Oakland.) | UNVERIFIED [2026-08-17] The laptop is an HP Pavilion with 32 GB RAM and a 512 GB disk. | reason: Contradictory location, newer is unverified
- NEEDS REVIEW (kept: [2026-10-05] The user lives in Oakland.) | UNVERIFIED [2026-08-18] The user lives in San Jose. | reason: Contradictory location, newer is unverified
- NEEDS REVIEW (kept: [2026-09-20] The user said they are not allergic to peanuts (joking, unverified).) | UNVERIFIED [2026-09-02] The user has a severe peanut allergy (confirmed by a doctor). | reason: Contradictory allergy, newer is unverified
- NEEDS REVIEW (kept: [2026-09-02] The user has a severe peanut allergy (confirmed by a doctor).) | UNVERIFIED [2026-09-20] The user said they are not allergic to peanuts (joking, unverified). | reason: Contradictory allergy, newer is unverified
- NEEDS REVIEW (kept: [2026-08-18] The user lives in San Jose.) | UNVERIFIED [2026-10-05] The user lives in Oakland. | reason: Contradictory location, newer is unverified
- KEPT [2026-09-09] The user runs all git commands (add, commit, push); the assistant only writes them out. | SUPERSEDED [2026-10-06] Do not execute git commands; give them to the user. | reason: Contradicted by newer line
