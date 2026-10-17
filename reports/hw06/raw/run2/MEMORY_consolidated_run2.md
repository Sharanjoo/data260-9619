# MEMORY.md
<!-- last-consolidated: 2026-10-16T07:15:50Z -->
<!-- format: one fact per bullet '- [YYYY-MM-DD] text'; tag [critical] for safety facts -->
## Facts
- [2026-08-12] The student is Sharan Lourduraj (Jo) at SJSU, course DATA-260.
- [2026-08-12] SID4 is 9619 and the PREFIX is s9619.
- [2026-08-12] SEED is 9619 and VERIFY_SEED is 269619.
- [2026-08-13] The repository is https://github.com/Sharanjoo/data260-9619.
- [2026-08-13] Collaborators on the repository are Sbnikitha and supriyaselvanganesan.
- [2026-08-17] The laptop is an HP Pavilion with 32 GB RAM and a 512 GB disk.
- [2026-08-22] The user wants a daily email digest of recalls. <!-- CONFLICT with the [2026-10-01] line, needs review -->
- [2026-08-25] DOMAIN_ID 3 means the grocery recall domain. <!-- merged duplicates L25, L36, L48 merged duplicates L4 -->
- [2026-08-27] Never run git commands yourself, hand them to the user. <!-- merged duplicates L7 -->
- [2026-09-01] Report font is Times New Roman, tables have green headers. <!-- merged duplicates L9, L43 merged duplicates L23 -->
- [2026-09-02] Every terminal screenshot must show the name Sharan Lourduraj. <!-- merged duplicates L10, L32, L47 -->
- [2026-09-02] [critical] The user has a severe peanut allergy (confirmed by a doctor).
- [2026-09-03] Model: qwen3:8b (Ollama, local, no paid API). <!-- merged duplicates L8, L45 -->
- [2026-09-04] The MongoDB database is s9619_doc, running as mongo:7.0 in Docker on host port 27017.
- [2026-09-05] The memory collections are messages, summaries and episodes.
- [2026-09-06] Episodic memory embeddings use nomic-embed-text served by Ollama.
- [2026-09-08] SHORT_TERM_N defaults to 12 and a session summary is written every 5 user messages.
- [2026-09-09] The user runs all git commands (add, commit, push); the assistant only writes them out. <!-- merged duplicates L38, L50 -->
- [2026-09-10] The Part 1 collection is recall_notices with a status enum and a category enum.
- [2026-09-14] In Postman, decline the AI Fix suggestion because it rewrites test bodies.
- [2026-09-18] qwen3:8b via Ollama is the chat model for every homework. <!-- merged duplicates L13 merged duplicates L21 -->
- [2026-09-19] The HW5 submission is tagged hw5 at commit 69fc4b5.
- [2026-09-20] The user said they are not allergic to peanuts (joking, unverified).
- [2026-09-23] Reports are exported as PDF named Lourduraj_HWn.pdf.
- [2026-09-26] The user prefers short answers.
- [2026-09-29] The user's partner is lactose intolerant. <!-- merged duplicates L40 -->
- [2026-09-30] The user shops at Safeway and Whole Foods.
- [2026-10-01] The user wants a weekly email digest of recalls. <!-- CONFLICT with the [2026-08-22] line, needs review -->
- [2026-10-02] The API runs on port 8619 (PORT_BASE).
- [2026-10-05] The user lives in Oakland.

## Resolved conflicts
- KEPT [2026-10-05] The user lives in Oakland. | SUPERSEDED [2026-08-18] The user lives in San Jose. | reason: Contradictory location, newer line is more recent.
- UNRESOLVED (both kept in Facts) [2026-08-22] The user wants a daily email digest of recalls. | [2026-10-01] The user wants a weekly email digest of recalls. | reason: Contradictory frequency, unverified newer line.
- KEPT [2026-10-02] The API runs on port 8619 (PORT_BASE). | SUPERSEDED [2026-08-30] The API runs on port 8000. | reason: Contradictory port, newer line is more recent.
