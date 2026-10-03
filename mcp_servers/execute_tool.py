"""HW5 Part 4: the single safe entry point for calling any of the three
Part 2B domain tools -- this is what Part 5's agent loop calls, and the
only thing it's allowed to call to reach the domain tools.

Design
------
execute_tool(name, inputs) looks `name` up in a tool registry (defaulting
to the three real domain_tools functions), calls it with `inputs` as
keyword arguments wrapped in Part 3's with_retry() bounded retry/backoff
policy, and ALWAYS returns the result as a JSON STRING in the shared
{ok, data, error} envelope -- never raises, regardless of what goes wrong:
an unknown tool name, malformed inputs, a tool-reported business-logic
failure (validation / not-found -- see Part 3's tool-contracts writeup),
or a genuine call-layer failure (DB connection hiccup, timeout).

Why wrapping with_retry() here is still correct even though domain_tools'
own functions already catch their own exceptions and return {ok: false,
...} as a normal return value (not a raise): with_retry only treats a
RAISED exception as a failed attempt. A domain tool returning {ok: false,
"error": "query must be a non-empty string"} is a normal, successful
return from with_retry's point of view -- so it is correctly NOT retried
(retrying a validation failure would never change the outcome). What IS
retried is a genuine failure to even get a response at all -- e.g.
SessionLocal() itself raising because of a transient DB connection issue,
which happens before domain_tools' own try/except block and so does
propagate as a real exception. This matches the Part 3.18 analysis
exactly: validation/not-found failures are rejected before or without
needing a retry; only the call-layer is what Part 3's policy protects.

Dependency injection
---------------------
`tools=` lets a caller substitute a fake registry instead of the real
database-backed one -- this is what the Part 4 offline test suite
(scripts/test_execute_tool_hw05.py) and the Part 5 MockModel agent tests
use, so neither ever needs a live database, network, or LLM to run.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from domain_tools import recall_detail, search_recalls, source_recall_summary  # noqa: E402
from retry_policy import with_retry  # noqa: E402

# The real tool registry -- maps the names Part 5's agent asks for to the
# real, database-backed domain_tools functions.
DEFAULT_TOOLS: Dict[str, Callable[..., dict]] = {
    "search_recalls": search_recalls,
    "recall_detail": recall_detail,
    "source_recall_summary": source_recall_summary,
}


def execute_tool(
    name: str,
    inputs: Optional[Dict[str, Any]] = None,
    *,
    tools: Optional[Dict[str, Callable[..., dict]]] = None,
    max_retries: int = 3,
    timeout_s: float = 0.25,
) -> str:
    """Call domain tool `name` with keyword arguments `inputs`. Always
    returns a JSON string of the {ok, data, error} envelope -- never
    raises.

    `tools`: dependency injection point; defaults to DEFAULT_TOOLS (the
    real, DB-backed functions). Tests pass a fake registry here instead.
    `max_retries`/`timeout_s`: passed through to with_retry() for the
    actual tool call (see module docstring for why only the call layer,
    not input validation, benefits from retrying).
    """
    inputs = inputs or {}
    registry = tools if tools is not None else DEFAULT_TOOLS

    tool_fn = registry.get(name)
    if tool_fn is None:
        return json.dumps(
            {
                "ok": False,
                "data": None,
                "error": f"unknown tool: {name!r} (available: {sorted(registry)})",
            }
        )

    outcome = with_retry(
        lambda: tool_fn(**inputs), max_retries=max_retries, timeout_s=timeout_s
    )

    if outcome.ok:
        # outcome.data IS the {ok, data, error} dict the tool itself
        # returned -- reused verbatim, not rebuilt.
        result = outcome.data
    else:
        # with_retry exhausted every attempt without ever getting a
        # response at all (a real exception/timeout on every try) -- build
        # the envelope fresh, since there's no tool-returned dict to reuse.
        result = {"ok": False, "data": None, "error": outcome.error}

    return json.dumps(result)
