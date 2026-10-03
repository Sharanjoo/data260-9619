# HW5 Part 3.18 - Tool Contracts Under Stress

Expected input schema, a rejected JSON input, and the returned error
output for each of the three domain tools from Part 2B
(`mcp_servers/domain_server.py`, logic in `mcp_servers/domain_tools.py`).
These are the same rejected-call examples captured as screenshots in
Part 2B -- no new rejected calls are run here, per the spec.

All three tools return the same shared envelope: `{"ok": bool, "data":
any, "error": string | null}`, with `error` non-null only when `ok` is
`false`.

## 1. `search_recalls` - search

**Expected input schema**
```json
{ "query": "string, non-empty after trim", "limit": "integer, 1-100 (default 10)" }
```

**Rejected JSON input**
```json
{ "query": "", "limit": 5 }
```

**Returned error output**
```json
{ "ok": false, "data": null, "error": "query must be a non-empty string" }
```

**Why rejected**: `query` fails the non-empty-after-`.strip()` check in
`search_recalls()` before any database call is made -- this is pure input
validation, not a database-level failure. A second rejected case for the
same tool, `limit=0` (or any value outside 1-100), is rejected for the
same reason by the next check: `{"ok": false, "data": null, "error":
"limit must be an integer between 1 and 100"}`.

## 2. `recall_detail` - detail lookup

**Expected input schema**
```json
{ "record_id": "integer" }
```

**Rejected JSON input**
```json
{ "record_id": 999999999 }
```

**Returned error output**
```json
{ "ok": false, "data": null, "error": "no recall record with id 999999999" }
```

**Why rejected**: `record_id` is a syntactically valid integer, so it
passes input validation, but `db.get(RecallRecord, record_id)` returns
`None` -- no row in `recall_record` has that primary key. This is a
business-logic/data-not-found rejection, not a validation error, and is
reported after a real (fast, indexed primary-key) query against the
database.

## 3. `source_recall_summary` - aggregate

**Expected input schema**
```json
{ "source_id": "integer" }
```

**Rejected JSON input**
```json
{ "source_id": 999999999 }
```

**Returned error output**
```json
{ "ok": false, "data": null, "error": "no recall source with id 999999999" }
```

**Why rejected**: same shape as `recall_detail` -- `source_id` is a valid
integer, but `db.get(RecallSource, source_id)` finds no matching row in
`recall_source`, so the aggregate (record count + total units_affected)
can never be computed for it.

## Summary

| Tool | Failure class | Caught before/after DB call | HTTP-equivalent |
|---|---|---|---|
| `search_recalls` | input validation (empty query / limit out of range) | before | 422 |
| `recall_detail` | not-found (valid input, no matching row) | after | 404 |
| `source_recall_summary` | not-found (valid input, no matching row) | after | 404 |

This split -- validation failures rejected before touching the database,
not-found failures reported only after a real query comes back empty -- is
also exactly what Part 3.19/3.20's retry policy needs to respect: a
validation failure is not something a retry would ever fix (retrying
`query=""` just fails the same way every time), so only the database-call
portion of each tool is wrapped in `with_retry()`, not the input
validation in front of it.
