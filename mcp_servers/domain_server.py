"""HW5 Part 2B: Domain MCP server (required) over s9619_rel.

Exactly three tools -- search, detail lookup, one aggregate operation --
backed by domain_tools.py, which defines the {ok, data, error} envelope
once (error is None on success). Part 4's execute_tool() reuses that same
module/envelope directly, so the logic and error strings here are
guaranteed identical to what execute_tool returns -- there is only one
implementation of each tool, this file just exposes it over MCP.

Run with the MCP Inspector:
    MYSQL_PORT=43306 mcp dev domain_server.py
(MYSQL_PORT=43306 matches compose.yaml's host-side MySQL port mapping --
this process runs on your host, not inside the `web` container, so it must
reach MySQL on the host-exposed port, not the container-internal default.)

Logging rule (STDIO transport): never write to stdout -- that corrupts the
JSON-RPC stream the Inspector/client talks over. All logging here goes to
stderr via the standard logging module.

Version pin note: `mcp dev <file>` launches this server via
`uv run --with mcp ... mcp run <file>`, which otherwise pulls the latest
`mcp` package (currently 2.x, where FastMCP was renamed/replaced). The
FastMCP(..., dependencies=[...]) call below adds "mcp[cli]<2" to that uv
invocation so it resolves to the last 1.x release instead -- no extra
flags needed when you run `mcp dev domain_server.py`.
"""
from __future__ import annotations

import logging
import sys

from mcp.server.fastmcp import FastMCP

from domain_tools import (
    recall_detail as _recall_detail,
    search_recalls as _search_recalls,
    source_recall_summary as _source_recall_summary,
)

logging.basicConfig(
    level=logging.INFO,
    stream=sys.stderr,
    format="%(asctime)s [domain_server] %(levelname)s: %(message)s",
)
logger = logging.getLogger("domain_server")

mcp = FastMCP("s9619_rel-domain", dependencies=["mcp[cli]<2", "requests", "sqlalchemy", "pymysql"])

# Diagnostic: log exactly which MySQL target this process resolved at import
# time (never the password). Lets you confirm in the Inspector's Console tab
# whether MYSQL_PORT etc. actually made it through npx/node's child-process
# spawn, instead of guessing from a generic 1045 Access Denied error.
import db as _db  # noqa: E402  (already importable: domain_tools did the sys.path.insert)
logger.info(
    "Resolved MySQL target -> host=%r port=%r db=%r user=%r (DATABASE_URL host/db only: %s)",
    _db.MYSQL_HOST, _db.MYSQL_PORT, _db.MYSQL_DB, _db.MYSQL_USER,
    _db.DATABASE_URL.split("@")[-1] if "@" in _db.DATABASE_URL else _db.DATABASE_URL,
)


@mcp.tool()
def search_recalls(query: str, limit: int = 10) -> dict:
    """Search recall records by product or brand name (case-insensitive
    substring match). Returns {ok, data, error}; data is a list of matching
    records on success."""
    logger.info("search_recalls query=%r limit=%r", query, limit)
    result = _search_recalls(query, limit)
    logger.info("search_recalls ok=%r", result["ok"])
    return result


@mcp.tool()
def recall_detail(record_id: int) -> dict:
    """Look up one recall record's full details by id. Returns
    {ok, data, error}; data is a single record object on success."""
    logger.info("recall_detail record_id=%r", record_id)
    result = _recall_detail(record_id)
    logger.info("recall_detail ok=%r", result["ok"])
    return result


@mcp.tool()
def source_recall_summary(source_id: int) -> dict:
    """Aggregate: record count and total units_affected for one recall
    source. Returns {ok, data, error}."""
    logger.info("source_recall_summary source_id=%r", source_id)
    result = _source_recall_summary(source_id)
    logger.info("source_recall_summary ok=%r", result["ok"])
    return result


if __name__ == "__main__":
    mcp.run(transport="stdio")
