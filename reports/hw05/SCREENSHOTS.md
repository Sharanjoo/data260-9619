# HW5 evidence checklist (matches the assignment text)

Rule from the assignment: for every question/sub-question put the **short code snippet and its output
together, one below the other**. Only relevant snippets, no full files. Your name must be visible in
every terminal screenshot. Headings 14 pt bold, sub-headings 12 pt bold, body 11 pt.

## Part 1.II - Postman (one screenshot per action tested) + DB

Log in first (`POST /api/hw4/auth/login`). Snippet above each: `code/db_routes.py` (lines in brackets).

| Action | Request | Expect |
|---|---|---|
| Source create [230-242] | `POST /sources` `{"source_name":"Test Source","source_region":"CA","source_code":"SRC-TEST-1"}` | 201 |
| Source list, paginated [244-255] | `GET /sources?limit=5&offset=0` | 200, 5 items |
| Source get one [257-263] | `GET /sources/<new id>` | 200 |
| Source update [265-282] | `PUT /sources/<new id>` change region | 200 |
| Relationship query [309-333] | `GET /sources/725/records?limit=5` | 200, records of source 725 |
| Record create [335-350] | `POST /records` with `source_id` = new source id | 201 |
| Record list [352-366] | `GET /records?limit=5` | 200 |
| Record get one [368-374] | `GET /records/<new record id>` | 200 |
| Record update [376-401] | `PUT /records/<new record id>` | 200 |
| Record delete [403-413] | `DELETE /records/<new record id>` | 200 |
| Source delete [284-307] | `DELETE /sources/<new id>` (after removing its records) | 200 |
| Error: not found | `GET /sources/999999` | 404 |
| Error: validation | `POST /sources` with `"source_code":"a b!"` | 422 |
| Error: duplicate | `POST /sources` same code twice | 409 |
| Error: delete protection | `DELETE /sources/725` | 409 (32 records) |

DB screenshot (terminal, name visible):
`docker exec -it data260-hw4-mysql-s9619 mysql -uhw4_user -phw4_pass_9619 s9619_rel -e "DESCRIBE recall_source; DESCRIBE recall_record;"`
plus the SELECT of the new source row. Snippet: `code/db.py` lines 84-128 (the two tables).

## Part 1.III - Redux: ONE screenshot per feature, code and UI in the SAME frame

Four screenshots (Home, Create, Update, Delete). Put VS Code (the thunk/slice snippet) and the browser
(the UI result) side by side and capture both in one image. Do not submit full files.

| Feature | Code to show | UI to show |
|---|---|---|
| Home | `Home.jsx` useSelector + `fetchRecords` (`recordsSlice.js` 21-36) | the list |
| Create | `createRecord` thunk (`recordsSlice.js` 38-57) | the new record in the list |
| Update | `fetchRecordById` + `updateRecord` thunks | `/update`: type an ID, Load record, edit, list shows change |
| Delete | `deleteRecord` thunk (`recordsSlice.js` ~79-89) | record gone from the list |

(Line numbers shifted slightly after the new `fetchRecordById` thunk was added; open the file and pick the thunk.)

## Part 2 - Inspector (labeled; input and output visible)

2A (meals): snippet = the tool in `meals_server.py` (116-131, 134-149, 152-160, 162-172), then the Inspector shot.
2B (domain): valid + invalid shot per tool; snippet `domain_server.py` 61-92 and `domain_tools.py` 49-52 (envelope).
Raw exports (required in `raw/`): copy each Inspector result JSON to
`reports/hw05/raw/inspector_<tool>.json` for all 7 tools.

## Part 3 / 4 / 5 - terminal runs (name visible)

Run each through the recorder so RUN_LOG.txt gets real timestamps:

```powershell
python scripts\recorded_run_hw05.py -- python scripts\demo_retry_scenarios_hw05.py      # 3.19 (3 scenarios)
python scripts\recorded_run_hw05.py -- python scripts\fault_injection_hw05.py          # 3.20 (needs MySQL) - re-run: not yet in RUN_LOG
python scripts\recorded_run_hw05.py -- python scripts\test_execute_tool_hw05.py        # Part 4/5.III
python scripts\recorded_run_hw05.py -- python scripts\demo_safety_rule_hw05.py         # 5.I
python scripts\recorded_run_hw05.py -- python scripts\run_agent_scenarios_hw05.py      # 5.IV (needs Ollama)
```

Snippets: `retry_policy.py` 60-117 (with_retry), `fault_injection_hw05.py` 53-75, `execute_tool.py` 69-139,
`test_execute_tool_hw05.py` (a few tests), `agent.py` 143-200 (run_agent loop). Keep each to ~10-25 lines.
