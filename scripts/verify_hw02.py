"""Homework 2 self-check"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SID4 = "9619"
SEED = "9619"
VERIFY_SEED = "269619"
PORT_BASE = 8619
BASE_URL = f"http://localhost:{PORT_BASE}"
MODEL = "qwen3:8b"


def get_commit_hash() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT,
                              capture_output=True, text=True, check=True)
        return out.stdout.strip()
    except Exception:
        return "unknown"


def http_get(path: str, timeout: float = 5.0):
    req = urllib.request.Request(f"{BASE_URL}{path}", method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


def http_post(path: str, payload: dict, timeout: float = 5.0):
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(f"{BASE_URL}{path}", data=body,
                                  headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


def wait_for_server(timeout_s: float) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            status, _ = http_get("/api/health")
            if status == 200:
                return True
        except Exception:
            pass
        time.sleep(1.0)
    return False


def main() -> int:
    checks = []
    started_server = False
    server_proc = None

    # Check 1: FastAPI backend responds on PORT_BASE 
    already_up = wait_for_server(timeout_s=2.0)
    if not already_up:
        server_proc = subprocess.Popen(
            [sys.executable, "main.py"],
            cwd=str(PROJECT_ROOT / "code"),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        started_server = True
        already_up = wait_for_server(timeout_s=20.0)
    checks.append({
        "name": "fastapi_backend_responds_on_port_base",
        "detail": f"GET {BASE_URL}/api/health",
        "passed": already_up,
    })

    if already_up:
        try:
            status, body = http_get("/api/notices")
            list_ok = status == 200 and isinstance(body, list)
        except Exception:
            list_ok = False
        checks.append({"name": "notices_list_returns_array", "passed": list_ok})

        try:
            marker = f"VERIFYTEST-{int(time.time())}"
            status, created = http_post("/api/notices", {
                "productName": marker,
                "brandName": "VerifyBrand",
                "category": "food-safety-recall",
                "description": "Automated smoke-test record.",
            })
            create_ok = status == 201 and created.get("productName") == marker
            status2, search_results = http_get(f"/api/notices?q={marker}")
            search_ok = status2 == 200 and any(n.get("productName") == marker for n in search_results)
            roundtrip_ok = create_ok and search_ok
        except Exception:
            roundtrip_ok = False
        checks.append({"name": "create_then_search_round_trip", "passed": roundtrip_ok})
    else:
        checks.append({"name": "notices_list_returns_array", "passed": False})
        checks.append({"name": "create_then_search_round_trip", "passed": False})

    if started_server and server_proc is not None:
        server_proc.terminate()
        try:
            server_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server_proc.kill()

    # Check 2: LangGraph stateful graph finishes and returns exactly 3 tags
    finished = False
    tags_ok = False
    with tempfile.TemporaryDirectory() as tmp_dir:
        output_path = Path(tmp_dir) / "verify_agent_graph_result.json"
        try:
            result = subprocess.run(
                [sys.executable, "code/agent_graph_demo.py",
                 "--input-file", "reports/hw02/cases/schema_input.json",
                 "--turn-ceiling", "6",
                 "--output-json", str(output_path)],
                cwd=str(PROJECT_ROOT),
                capture_output=True, text=True, timeout=180,
            )
            finished = result.returncode == 0
            if finished and output_path.exists():
                data = json.loads(output_path.read_text(encoding="utf-8"))
                proposal = data.get("planner_proposal")
                tags_ok = bool(
                    proposal and isinstance(proposal.get("tags"), list) and len(proposal["tags"]) == 3
                )
        except subprocess.TimeoutExpired:
            finished = False

    checks.append({"name": "langgraph_finishes_without_hanging", "passed": finished})
    checks.append({"name": "langgraph_returns_exactly_three_tags", "passed": tags_ok})

    all_passed = all(c["passed"] for c in checks)

    verification = {
        "homework": "hw02",
        "sid4": SID4,
        "commit_hash": get_commit_hash(),
        "model": MODEL,
        "seed": SEED,
        "verify_seed": VERIFY_SEED,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
        "all_checks_passed": all_passed,
    }

    output_file = PROJECT_ROOT / "reports" / "hw02" / "verification.json"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(json.dumps(verification, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(json.dumps(verification, indent=2, ensure_ascii=False))
    print(f"\nSaved: {output_file}")
    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())