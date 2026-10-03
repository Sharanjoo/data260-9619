# HW5 Part 2 - MCP Tool Servers

Two local MCP servers, both STDIO transport, both debugged with the MCP
Inspector (`mcp dev <file>`). Run these on your host machine (not inside
the `web` Docker container) -- the Inspector opens a browser UI that the
container can't serve.

## Setup (once)

```powershell
cd mcp_servers
pip install -r requirements.txt
```

### Why "Connecting..." can fail / the `mcp<2` pin

`mcp dev <file>` doesn't actually run your locally pip-installed `mcp`
package -- it shells out to `uv run --with mcp ... mcp run <file>`, which
builds a **fresh, separate** environment via `uv` and otherwise grabs
whatever the latest `mcp` on PyPI is (currently 2.x, where `FastMCP` was
renamed/replaced by `MCPServer`). If you see the Inspector hang on
"Connecting..." and then fail, that's why: the subprocess uv built
couldn't `from mcp.server.fastmcp import FastMCP`.

Both server files already work around this: `FastMCP(..., dependencies=[
"mcp[cli]<2", ...])` adds that pin to the `uv run --with ...` command `mcp
dev` builds automatically, so running `mcp dev meals_server.py` (no extra
flags) resolves to the last 1.x `mcp` release, which still has `FastMCP`.
This was verified directly against the actual `mcp.cli.cli` command-builder
in this repo's dev environment -- no guessing.

If the Inspector still fails to connect after this, check: (1) `uv` is
installed and on PATH (`uv --version`), since `mcp dev` depends on it; (2)
Node/npm's `npx` is available, since the Inspector itself is an npm
package `mcp dev` launches via `npx @modelcontextprotocol/inspector`.

## A. `meals_server.py` - TheMealDB tutorial server (Part 2A)

No local dependencies beyond the above -- it only talks to the public
TheMealDB API over HTTPS using the published test key `1`.

```powershell
mcp dev meals_server.py
```

Four tools: `search_meals_by_name`, `meals_by_ingredient`, `random_meal`,
`meal_details`. Try each in the Inspector (e.g. query "Arrabiata",
ingredient "chicken") and screenshot the input + output for each of the
four, per the spec.

## B. `domain_server.py` - domain server over `s9619_rel` (Part 2B, required)

This one talks to your MySQL database via `code/db.py`, so MySQL must be
running (`docker compose up -d`) first. Because this process runs on your
host rather than inside the `web` container, it needs the **host-side**
MySQL port from `compose.yaml` (`43306`), not the container-internal
default of `3306`:

```powershell
mcp dev domain_server.py
```

(You do NOT need to set `MYSQL_PORT` yourself -- `domain_tools.py` already
defaults it to `43306` to match `compose.yaml`'s host-side MySQL port
mapping. This was originally meant to be set via `$env:MYSQL_PORT`, but on
Windows, launching through `npx @modelcontextprotocol/inspector` spawns
Python via Node's `child_process`, which does not reliably forward a parent
shell's env vars -- confirmed directly: setting `$env:MYSQL_PORT` in
PowerShell before the command did not reach the spawned process, which
silently fell back to port `3306` and connected to a *different* MySQL
server than the Docker one, with its own confusing "Access denied" error.
The default now lives in the code instead of relying on env var passthrough.)

Three tools, each returning the shared `{ok, data, error}` envelope
(`error` is `null` on success):

- `search_recalls(query, limit=10)` - search
- `recall_detail(record_id)` - detail lookup
- `source_recall_summary(source_id)` - aggregate (record count + total
  units_affected for one source)

For each of the three tools, run **one valid call and one intentionally
invalid call** in the Inspector and screenshot both (per the spec -- these
are the rejected-call examples Part 3 writes up):

| Tool | Valid example | Invalid example |
|---|---|---|
| `search_recalls` | `query="milk", limit=5` | `query=""` (empty) or `limit=0` |
| `recall_detail` | an id you know exists (check the DB or a prior `search_recalls` result) | `record_id=999999999` (doesn't exist) |
| `source_recall_summary` | a `source_id` you know exists | `source_id=999999999` (doesn't exist) |

## Shared logic

`domain_tools.py` holds the actual implementation (DB queries, validation,
envelope) for all three domain tools, with no MCP import at all.
`domain_server.py` is a thin MCP wrapper around it, and HW5 Part 4's
`execute_tool()` will import `domain_tools.py` directly -- same functions,
same envelope, same error strings, defined exactly once.
