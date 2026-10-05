# HW5 screenshot checklist

Save every image into `reports/hw05/screenshots/` with the exact filename shown.
`build_report_hw05.py` picks them up by those names, and anything missing is
marked as MISSING in the PDF so you can see what is left.

## Before you start: put your name in every terminal

PowerShell prompt that shows your name on every line (paste once per window):

```powershell
function prompt { "Sharan Lourduraj | PS $($executionContext.SessionState.Path.CurrentLocation)> " }
```

Then `cd` to the repo root. Use `python scripts\recorded_run_hw05.py -- <command>`
for the terminal runs below so each one also lands in `reports/hw05/RUN_LOG.txt`
with a timestamp. Start Docker (`docker compose up -d`) and Ollama first.

## Part 1.II: Postman and database (log in first; use the session cookie)

| File | What to show |
|---|---|
| p1_postman_source_create.png | POST /api/hw4/sources, 201, body `{"source_name":"Test Source","source_region":"CA","source_code":"SRC-TEST-1"}` |
| p1_postman_source_conflict.png | the same POST again (duplicate `source_code`), 409 |
| p1_postman_source_records.png | GET /api/hw4/sources/725/records (relationship query) |
| p1_postman_source_delete_blocked.png | DELETE /api/hw4/sources/725, 409 with the dependent-count message |
| p1_db_rows.png | `docker exec -it data260-hw4-mysql-s9619 mysql -uhw4_user -phw4_pass_9619 s9619_rel -e "SELECT id,source_code,source_name FROM recall_source ORDER BY id DESC LIMIT 5;"` |

## Part 1.III: Redux, one pair per page

For each page, one screenshot of the Redux code and one of the running UI
(`npm run dev` in `client/`).

| File | What to show |
|---|---|
| p1_redux_store.png | `client/src/store.js` and the thunks in `recordsSlice.js` |
| p1_home_code.png / p1_home_ui.png | `Home.jsx` using useSelector/useDispatch, and the list page |
| p1_create_code.png / p1_create_ui.png | `CreateRecord.jsx`, then a record created in the UI |
| p1_update_code.png / p1_update_ui.png | `UpdateRecord.jsx`, then a record updated |
| p1_delete_code.png / p1_delete_ui.png | `DeleteRecord.jsx`, then a record deleted |

## Part 2A: Inspector, one screenshot per MealDB tool

```powershell
cd mcp_servers
npx @modelcontextprotocol/inspector python meals_server.py
```

| File | Tool and input |
|---|---|
| p2a_search_meals_by_name.png | `query = "chicken"`, `limit = 3` |
| p2a_meals_by_ingredient.png | `ingredient = "chicken_breast"` |
| p2a_random_meal.png | no input |
| p2a_meal_details.png | `id = "52772"` |

## Part 2B: Inspector, valid and invalid per domain tool (6 shots)

```powershell
cd mcp_servers
npx @modelcontextprotocol/inspector python domain_server.py
```

| File | Input |
|---|---|
| p2b_search_recalls_valid.png | `query = "juice"`, `limit = 5` |
| p2b_search_recalls_invalid.png | `query = ""` |
| p2b_recall_detail_valid.png | `record_id = 15007` |
| p2b_recall_detail_invalid.png | `record_id = 999999999` |
| p2b_source_summary_valid.png | `source_id = 725` |
| p2b_source_summary_invalid.png | `source_id = 999999` |

Also copy each tool's JSON result (the Inspector result panel) into
`reports/hw05/raw/inspector_<tool_name>.json`. That is 7 files:
the 4 meal tools plus the 3 domain tools.

## Part 3: retry scenarios (terminal)

```powershell
python scripts\recorded_run_hw05.py -- python scripts\demo_retry_scenarios_hw05.py
```

Screenshot: p3_retry_scenarios.png (all three scenarios visible).

## Part 4: test runner (terminal)

```powershell
python scripts\recorded_run_hw05.py -- python scripts\test_execute_tool_hw05.py
```

Screenshot: p4_tests.png (nine PASS lines plus the `9/9 tests passed` summary).

## Part 5: safety rule and agent scenarios (terminal)

```powershell
python scripts\recorded_run_hw05.py -- python scripts\demo_safety_rule_hw05.py
python scripts\recorded_run_hw05.py -- python scripts\run_agent_scenarios_hw05.py
```

Screenshots: p5_safety_rule.png (allowed call, then blocked call) and
p5_agent_scenarios.png (the four-row METRICS table at the end).

Note: the agent run appends to `raw/agent_runs.jsonl`, so running it again adds
four more lines. If you re-run it, tell me and I will refresh METRICS.md and
REFLECTION.md from the new log rather than leaving them pointing at old run ids.

## What to capture in the Redux code screenshots

| File | Show (client/src/...) |
|---|---|
| p1_redux_store.png | `store.js` (configureStore) and `recordsSlice.js` lines 21-90 (the four createAsyncThunk calls) |
| p1_home_code.png | `components/Home.jsx` lines 3-22 (useDispatch, useSelector, dispatch(fetchRecords())) |
| p1_create_code.png | `components/CreateRecord.jsx` lines 3-42 (useDispatch, dispatch(createRecord(...)).unwrap()) |
| p1_update_code.png | `components/UpdateRecord.jsx` lines 3-60 |
| p1_delete_code.png | `components/DeleteRecord.jsx` lines 3-45 |

`main.jsx` wraps the app in `<Provider store={store}>`; include it in the store shot if it fits.

## Suggested order (fewest restarts)

1. Terminal runs (Part 4, 3, 5 safety), no browser needed.
2. Postman + database (Part 1.II) with Docker up.
3. `npm run dev` and the Redux UI shots (Part 1.III).
4. Inspector: meals server, then domain server (Part 2A, 2B), plus the 7 raw JSON exports.
5. Agent scenarios last (needs Ollama), then tell the assistant so METRICS/REFLECTION are refreshed from the new log.
