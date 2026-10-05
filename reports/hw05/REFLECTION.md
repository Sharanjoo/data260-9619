# HW5 Part 5.V - Reflection

I chose run `36e27e9a` from `reports/hw05/raw/agent_runs.jsonl`: the multi-step scenario, "Look up recall record 15007, then tell me the record count and total units affected across all recalls from the same source." It ran with `max_steps=5` on the local `qwen3:8b` model through Ollama.

**Step 1.** The harness sent the system prompt (the three tools plus the one-JSON-object-per-turn rule) and the user request. The model replied with a `call_tool` action for `recall_detail` with `record_id` 15007. The harness parsed the JSON and passed it to `execute_tool`, never to the domain function directly. The safety rule only checks `search_recalls` limits, so it didn't apply. The result was `ok=true` and included `source_id` 725. The harness logged the full result and fed a compacted copy back to the model.

**Step 2.** The model chose `source_recall_summary` with `source_id` 725, a value it could only know from step 1's output. That chaining is the point of the scenario. `execute_tool` returned `ok=true`: 32 records and 0 total units affected.

**Step 3.** The model replied with a `final_answer`. The harness recorded the text, set `stop_reason` to `normal_completion`, and left the loop after 3 of the 5 allowed steps, so the `max_steps` ceiling was never reached.

The other stop reasons look different. The limit-50 scenario ended at step 1 with `safety_rule_block`: `execute_tool` refused before touching the database, and the harness stopped instead of letting the model retry. The `MockModel` test shows the ceiling, where a model that never answers is cut off after exactly `max_steps` turns.

One caveat: every seeded record has `units_affected = 0`, so the "0 units" answer is correct but uninformative.
