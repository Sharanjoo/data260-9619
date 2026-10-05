"""HW5 self-check: confirms the FastAPI backend answers on PORT_BASE, that both
MCP servers start and answer a tool call over STDIO, that the Part 4/5 safety
logic and offline tests pass, and that the required raw outputs exist. Writes
reports/hw05/verification.json.

Run the app first (docker compose up -d); Ollama is only needed for the
"ollama has the model" check. Does not modify any application code; it only
reads the live API / starts the MCP servers as subprocesses / reads the repo's
own output files, then writes the verification JSON.

Usage (repo root):
    python scripts/verify_hw05.py
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
MCP_DIR = REPO_ROOT / "mcp_servers"
RAW = REPO_ROOT / "reports" / "hw05" / "raw"

# Host-side scripts must use the host-mapped MySQL port from compose.yaml (43306).
os.environ.setdefault("MYSQL_HOST", "127.0.0.1")
os.environ.setdefault("MYSQL_PORT", "43306")
os.environ.setdefault("MYSQL_USER", "hw4_user")
os.environ.setdefault("MYSQL_PASSWORD", "hw4_pass_9619")
os.environ.setdefault("MYSQL_DB", "s9619_rel")

BASE_URL = "http://localhost:8619"
OLLAMA_URL = "http://localhost:11434"

HOMEWORK_NUMBER = 5
SID4 = 9619
PORT_BASE = 8619
SEED = 9619
VERIFY_SEED = 269619
MODEL_CONFIG = "qwen3:8b via Ollama (agent loop, think=False, temperature=0, max_steps=5); MCP over STDIO (mcp[cli]<2)"
MCP_TIMEOUT_S = 60

MEALS_TOOLS = {"search_meals_by_name", "meals_by_ingredient", "random_meal", "meal_details"}
DOMAIN_TOOLS = {"search_recalls", "recall_detail", "source_recall_summary"}
INSPECTOR_FILES = [f"inspector_{t}.json" for t in sorted(MEALS_TOOLS | DOMAIN_TOOLS)]

checks: list[dict] = []


def record(name: str, passed: bool, detail: str = "") -> None:
    checks.append({"check": name, "passed": bool(passed), "detail": detail})
    print(f"[{'PASS' if passed else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""), flush=True)


def get_commit_hash() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True,
                                       stderr=subprocess.DEVNULL).strip()
    except Exception:
        return "unknown (not a git checkout, or git unavailable)"


# ---------------------------------------------------------------- FastAPI backend
def check_backend() -> None:
    try:
        r = requests.get(f"{BASE_URL}/api/health", timeout=5)
        ok = r.status_code == 200 and r.json().get("port") == PORT_BASE
        record("backend_responds_on_port_base", ok, f"GET /api/health -> {r.status_code} {r.text[:80]}")
    except requests.exceptions.RequestException as exc:
        record("backend_responds_on_port_base", False, f"{type(exc).__name__} on {BASE_URL} -- is docker compose up?")
    try:
        r = requests.get(f"{BASE_URL}/api/hw4/sources", timeout=5)
        record("backend_protects_hw5_routes_without_login", r.status_code == 401,
               f"GET /api/hw4/sources without a session -> {r.status_code} (expected 401)")
    except requests.exceptions.RequestException as exc:
        record("backend_protects_hw5_routes_without_login", False, f"{type(exc).__name__}")


# ---------------------------------------------------------------- MCP servers (STDIO)
def _payload(result) -> dict | None:
    for item in getattr(result, "content", []) or []:
        text = getattr(item, "text", None)
        if text:
            try:
                return json.loads(text)
            except ValueError:
                return {"_raw": text[:200]}
    return None


async def _probe_server(script: str, calls: list[tuple[str, dict]]):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(command=sys.executable, args=[str(MCP_DIR / script)],
                                   cwd=str(MCP_DIR), env={**os.environ})
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = {t.name for t in (await session.list_tools()).tools}
            results = []
            for name, args in calls:
                res = await session.call_tool(name, args)
                results.append((name, bool(getattr(res, "isError", False)), _payload(res)))
            return tools, results


def probe(label: str, script: str, expected_tools: set[str], calls: list[tuple[str, dict]], judge) -> None:
    try:
        tools, results = asyncio.run(asyncio.wait_for(_probe_server(script, calls), MCP_TIMEOUT_S))
    except Exception as exc:  # startup failure, timeout, protocol error
        msg = f"{type(exc).__name__}: {str(exc)[:150]}"
        record(f"{label}_starts_and_lists_tools", False, msg)
        for name, _ in calls:
            record(f"{label}_{name}_answers", False, "skipped -- server did not start")
        return
    record(f"{label}_starts_and_lists_tools", expected_tools <= tools, f"tools={sorted(tools)}")
    for (name, is_err, payload), (_, args) in zip(results, calls):
        passed, detail = judge(name, args, is_err, payload)
        record(f"{label}_{name}_answers", passed, detail)


def judge_meals(name, args, is_err, payload):
    if is_err:
        return False, f"isError from tool; payload={str(payload)[:140]} (needs internet to TheMealDB)"
    meals = (payload or {}).get("meals") if isinstance(payload, dict) else None
    return bool(meals), f"returned {len(meals or [])} meal(s) for {args}"


def judge_domain(name, args, is_err, payload):
    if not isinstance(payload, dict):
        return False, f"no JSON envelope returned (isError={is_err}, payload={str(payload)[:100]})"
    if name == "recall_detail":  # invalid-input call: must be the clean "not found" envelope (not a DB outage or crash)
        err = str(payload.get("error"))
        return payload.get("ok") is False and "no recall record with id" in err, f"ok={payload.get('ok')} error={err[:110]}"
    return payload.get("ok") is True and bool(payload.get("data")), f"ok={payload.get('ok')} error={payload.get('error')}"


# ---------------------------------------------------------------- offline logic + files
def check_safety_rule() -> None:
    try:
        sys.path.insert(0, str(MCP_DIR))
        from execute_tool import execute_tool

        out = json.loads(execute_tool("search_recalls", {"query": "a", "limit": 50}))
        record("execute_tool_blocks_search_recalls_limit_over_25",
               out.get("ok") is False and "safety rule" in str(out.get("error")), str(out.get("error"))[:110])
    except Exception as exc:
        record("execute_tool_blocks_search_recalls_limit_over_25", False, f"{type(exc).__name__}: {exc}")


def check_offline_tests() -> None:
    try:
        p = subprocess.run([sys.executable, str(REPO_ROOT / "scripts" / "test_execute_tool_hw05.py")],
                           cwd=REPO_ROOT, capture_output=True, text=True, timeout=120)
        record("part4_offline_test_suite_passes", p.returncode == 0 and "9/9" in p.stdout,
               (p.stdout.strip().splitlines() or ["no output"])[-1])
    except Exception as exc:
        record("part4_offline_test_suite_passes", False, f"{type(exc).__name__}: {exc}")


def check_raw_and_docs() -> None:
    try:
        s = json.loads((RAW / "fault_injection_summary.json").read_text(encoding="utf-8"))
        rates = [r["injected_failure_rate"] for r in s["results"]]
        record("part3_fault_injection_summary_present", rates == [0.0, 0.2, 0.5] and s.get("seed_used") == VERIFY_SEED,
               f"rates={rates}, seed_used={s.get('seed_used')}")
    except Exception as exc:
        record("part3_fault_injection_summary_present", False, f"{type(exc).__name__}: {exc}")

    try:
        lines = [json.loads(x) for x in (RAW / "agent_runs.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
        reasons = {r.get("stop_reason") for r in lines}
        record("part5_agent_runs_logged_with_stop_reasons",
               {"normal_completion", "safety_rule_block"} <= reasons and len(lines) >= 4,
               f"{len(lines)} run(s), stop reasons={sorted(reasons)}")
    except Exception as exc:
        record("part5_agent_runs_logged_with_stop_reasons", False, f"{type(exc).__name__}: {exc}")

    missing = [f for f in INSPECTOR_FILES if not (RAW / f).exists() or (RAW / f).stat().st_size == 0]
    record("part2_inspector_exports_present_for_all_7_tools", not missing,
           "all 7 present" if not missing else "missing: " + ", ".join(missing))

    docs = ["METRICS.md", "REFLECTION.md", "AI_USE.md", "RUN_LOG.txt"]
    bad = [d for d in docs if not (REPO_ROOT / "reports" / "hw05" / d).exists()
           or (REPO_ROOT / "reports" / "hw05" / d).stat().st_size == 0]
    record("writeups_present_and_non_empty", not bad, "all present" if not bad else "missing/empty: " + ", ".join(bad))

    ai = REPO_ROOT / "reports" / "hw05" / "AI_USE.md"
    if not ai.exists():
        record("ai_use_has_no_leftover_draft_note", False, "AI_USE.md missing")
    else:
        has_draft = "DRAFT written by the assistant" in ai.read_text(encoding="utf-8")
        record("ai_use_has_no_leftover_draft_note", not has_draft,
               "still contains the '> DRAFT ...' note -- review the file and delete it" if has_draft else "draft note removed")


def check_ollama() -> None:
    try:
        names = [m.get("name", "") for m in requests.get(f"{OLLAMA_URL}/api/tags", timeout=5).json().get("models", [])]
        record("ollama_reachable_with_qwen3_8b", any(n.startswith("qwen3:8b") for n in names), f"models={names[:5]}")
    except requests.exceptions.RequestException as exc:
        record("ollama_reachable_with_qwen3_8b", False, f"{type(exc).__name__} on {OLLAMA_URL}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(REPO_ROOT / "reports" / "hw05" / "verification.json"))
    args = ap.parse_args()

    check_backend()
    probe("meals_server", "meals_server.py", MEALS_TOOLS,
          [("search_meals_by_name", {"query": "chicken", "limit": 1})], judge_meals)
    probe("domain_server", "domain_server.py", DOMAIN_TOOLS,
          [("search_recalls", {"query": "juice", "limit": 1}), ("recall_detail", {"record_id": 999999999})],
          judge_domain)
    check_safety_rule()
    check_offline_tests()
    check_raw_and_docs()
    check_ollama()

    passed = sum(1 for c in checks if c["passed"])
    result = {
        "homework_number": HOMEWORK_NUMBER,
        "sid4": SID4,
        "commit_hash": get_commit_hash(),
        "model_configuration": MODEL_CONFIG,
        "seed": SEED,
        "verify_seed": VERIFY_SEED,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "checks_passed": passed,
        "checks_total": len(checks),
        "all_passed": passed == len(checks),
        "checks": checks,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(checks)} checks passed.\nWrote {out}")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
