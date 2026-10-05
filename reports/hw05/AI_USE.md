# AI_USE.md HW5 (SID4 9619)

## 1. What I used an AI assistant for, and what I did myself

I used an AI assistant to write and revise the HW5 code and write-ups: the Redux Toolkit migration of the React client (Part 1.III), the domain safety rule and the agent loop (Part 5), and drafts of METRICS.md, REFLECTION.md.

What I did myself: Executed (Docker, MySQL, npm, Python scripts, Ollama with qwen3:8b, the MCP Inspector, Postman and the browser), reviewed the output, took all the screenshots, and made every git commit and push myself.

## 2. One AI-produced output that was wrong or unsuitable

The assistant wrote the first set of Part 5 agent scenarios using IDs and search terms it had not checked against my seeded data: recall record 1, recall source 1, and the search word "milk". None of those exist in my database (seeded record ids start near 15007, and "milk" has no matches). The scenarios still "ran", but every tool call came back "not found" and the agent politely reported that, so the table looked fine while proving nothing about real tool results.

## 3. How it was detected

From the real run output. Each answer said the record or source was not found, and the logged tool results were empty or errors. I also noticed the run was slow and that the "aggregate" scenario had nothing to aggregate. I then looked at what is actually in the database: record 15007 exists, belongs to source 725 ("Local Public Health Unit #125", SRC-00725), that source has 32 records, and the word "juice" has matches while "milk" does not.

## 4. What changed, and why it works now

The scenarios in `scripts/run_agent_scenarios_hw05.py` now use data that exists: search for "juice", detail for record 15007, and a multi-step run that looks up record 15007 and then summarises its source (725). I kept the first-pass log as `reports/hw05/raw/agent_runs_first_pass_nonexistent_ids.jsonl` instead of deleting it, and the table in METRICS.md comes from the second pass. The multi-step run (id 36e27e9a) now makes two real tool calls, `recall_detail` then `source_recall_summary`, and finishes in three steps. Separately, the model was too slow, so the agent now calls Ollama with `think=False` and feeds only the first 3 records of each tool result back to the model while still logging the full result.
