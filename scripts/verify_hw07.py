"""HW7 self-check (make verify-hw07): objective behaviour checks for Parts 1-6 plus the required deliverables.

Live checks (need `docker compose up -d`, the backend on PORT_BASE, migrate_hw07.py + seed_users_hw07.py run once, and
Ollama with qwen3:8b): POST /auth/login (token for valid credentials, 401 for invalid), GET /auth/me, role-based access on
/api/hw4/sources (401 / 403 / 201 / 200), and one real agent-loop task run through the HW1 adapter.
Offline checks: every HW7 test suite, the safety gate on 5 allowed + 5 blocked commands, the independent bike-share
reference calculation for both scenarios (>= 500 trips each, correct winner), the pricing-page snapshots' SHA-256 hashes,
the prompt-injection fixture, and the presence of the raw data files.
It does NOT modify application code: it hashes code/ and src/ before and after and records the result as a check.

Usage (repo root):   python scripts/verify_hw07.py          (writes reports/hw07/verification.json)
                     python scripts/verify_hw07.py --skip-live-model     (skip the one real model call)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
REPORT_DIR = REPO_ROOT / "reports" / "hw07"
RAW = REPORT_DIR / "raw"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

BASE_URL = "http://localhost:8619"
OLLAMA_URL = "http://localhost:11434"
HOMEWORK_NUMBER = 7
SID4 = 9619
PORT_BASE = 8619
SEED = 9619
VERIFY_SEED = 269619
MODEL_CONFIG = ("qwen3:8b via Ollama (temperature 0) + nomic-embed-text; JWT bearer auth (reader/writer/moderator) on MySQL users; "
                "hand-written tool loop (max 8 iterations, 2 repairs); Reflexion (max 2 retries, 14 tool calls, 24000 tokens); "
                "LangChain create_agent (LangGraph ReAct) bike-share agent; file tools + safety gate")
USERS = {"reader1": "Reader#9619", "writer1": "Writer#9619", "moderator1": "Moderator#9619"}

checks: list[dict] = []
info: dict = {}


def record(name: str, passed: bool, detail: str = "") -> None:
    checks.append({"check": name, "passed": bool(passed), "detail": detail})
    print(f"[{'PASS' if passed else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""), flush=True)


def get_commit_hash() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:  # noqa: BLE001
        return "unknown (not a git checkout, or git unavailable)"


def tree_hash(*folders: str) -> str:
    digest = hashlib.sha256()
    for folder in folders:
        for path in sorted((REPO_ROOT / folder).rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
                digest.update(str(path.relative_to(REPO_ROOT)).encode())
                digest.update(path.read_bytes())
    return digest.hexdigest()


# ---------------------------------------------------------------- Part 1: JWT auth (live)
def _auth(token):
    return {"Authorization": f"Bearer {token}"} if token else {}


def check_auth(rng: random.Random) -> None:
    try:
        r = requests.post(f"{BASE_URL}/auth/login", json={"username": "writer1", "password": USERS["writer1"]}, timeout=15)
    except requests.RequestException as exc:
        record("backend_reachable", False, f"{type(exc).__name__} on {BASE_URL} (docker compose up -d; python code/main.py or the compose backend)")
        return
    record("backend_reachable", True, BASE_URL)
    body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    record("login_valid_returns_token", r.status_code == 200 and bool(body.get("access_token")), f"HTTP {r.status_code}, token_type={body.get('token_type')}")
    bad = requests.post(f"{BASE_URL}/auth/login", json={"username": "writer1", "password": "not-the-password"}, timeout=15)
    ghost = requests.post(f"{BASE_URL}/auth/login", json={"username": "nobody", "password": "x"}, timeout=15)
    record("login_invalid_returns_401", bad.status_code == 401 and ghost.status_code == 401, f"wrong password HTTP {bad.status_code}, unknown user HTTP {ghost.status_code}")

    tokens = {}
    for user, pw in USERS.items():
        resp = requests.post(f"{BASE_URL}/auth/login", json={"username": user, "password": pw}, timeout=15)
        tokens[user] = resp.json().get("access_token") if resp.status_code == 200 else None
    record("three_roles_can_log_in", all(tokens.values()), f"{sum(1 for t in tokens.values() if t)}/3 demo users")

    no_tok = requests.get(f"{BASE_URL}/auth/me", timeout=15)
    me = requests.get(f"{BASE_URL}/auth/me", headers=_auth(tokens["writer1"]), timeout=15)
    record("auth_me_requires_token_and_reports_role", no_tok.status_code == 401 and me.status_code == 200 and me.json().get("role") == "writer",
           f"no token HTTP {no_tok.status_code}; with token HTTP {me.status_code} role={me.json().get('role') if me.status_code == 200 else None}")
    tampered = (tokens["writer1"] or "x")[:-4] + "AAAA"
    record("tampered_token_rejected", requests.get(f"{BASE_URL}/auth/me", headers=_auth(tampered), timeout=15).status_code == 401)

    body = {"source_name": f"HW7 verify {rng.randint(1000, 9999)}", "source_region": "Pacific Southwest"}
    as_reader = requests.post(f"{BASE_URL}/api/hw4/sources", headers=_auth(tokens["reader1"]), json=body, timeout=15)
    as_writer = requests.post(f"{BASE_URL}/api/hw4/sources", headers=_auth(tokens["writer1"]), json=body, timeout=15)
    record("rbac_reader_cannot_create_writer_can", as_reader.status_code == 403 and as_writer.status_code == 201,
           f"reader HTTP {as_reader.status_code}, writer HTTP {as_writer.status_code}")
    listing = requests.get(f"{BASE_URL}/api/hw4/sources?limit=2", headers=_auth(tokens["reader1"]), timeout=15)
    unauth = requests.get(f"{BASE_URL}/api/hw4/sources?limit=2", timeout=15)
    record("rbac_list_needs_a_valid_token", listing.status_code == 200 and unauth.status_code == 401, f"reader HTTP {listing.status_code}, no token HTTP {unauth.status_code}")
    if as_writer.status_code == 201:
        sid = as_writer.json()["id"]
        by_writer = requests.delete(f"{BASE_URL}/api/hw4/sources/{sid}", headers=_auth(tokens["writer1"]), timeout=15)
        by_mod = requests.delete(f"{BASE_URL}/api/hw4/sources/{sid}", headers=_auth(tokens["moderator1"]), timeout=15)
        record("rbac_delete_moderator_only", by_writer.status_code == 403 and by_mod.status_code in (200, 204),
               f"writer HTTP {by_writer.status_code}, moderator HTTP {by_mod.status_code} (temporary row removed)")
    else:
        record("rbac_delete_moderator_only", False, "could not create the temporary row to delete")


# ---------------------------------------------------------------- Parts 2-6: offline suites
SUITES = ["test_jwt_auth_hw07.py", "test_agent_loop_hw07.py", "test_reflexion_hw07.py", "test_file_tools_hw07.py",
          "test_safety_gate_hw07.py", "test_bike_tools_hw07.py", "test_bike_agent_hw07.py", "test_injection_hw07.py"]


def check_offline_suites() -> None:
    for script in SUITES:
        try:
            p = subprocess.run([sys.executable, str(REPO_ROOT / "scripts" / script)], cwd=REPO_ROOT, capture_output=True, text=True, timeout=600)
            lines = [ln for ln in p.stdout.strip().splitlines() if ln.strip()]
            err = [ln for ln in p.stderr.strip().splitlines() if ln.strip()]
            last = lines[-1] if lines else ("stderr: " + err[-1] if err else "no output")
            record(f"suite_{script.replace('.py', '')}", p.returncode == 0 and "checks passed" in last, last)
        except Exception as exc:  # noqa: BLE001
            record(f"suite_{script.replace('.py', '')}", False, f"{type(exc).__name__}: {exc}")


def check_safety_gate() -> None:
    from src.safety_gate import confirm_bash, is_destructive  # noqa: PLC0415

    allowed = ["ls -la", "cat README.md", "git status", "grep -rn DEBUG .", "head -n 5 notes.txt"]
    blocked = ["rm -rf /", "sudo apt-get install nmap", "chmod -R 777 /", "dd if=/dev/zero of=/dev/sda", "echo x > /etc/passwd"]
    a = [confirm_bash(c)["allowed"] for c in allowed]
    b = [not confirm_bash(c)["allowed"] for c in blocked]
    record("safety_gate_5_pass_5_blocked", all(a) and all(b), f"allowed {sum(a)}/5, blocked {sum(b)}/5")
    record("safety_gate_confirmation_never_implicit", not confirm_bash("rm -rf /", auto_approve=True)["allowed"] and is_destructive("rm -rf /tmp/x"),
           "auto_approve cannot override a destructive command")


def check_bike_references() -> None:
    import csv  # noqa: PLC0415

    from src.bike_pricing import evaluate_trips  # noqa: PLC0415

    for key, csv_name, winner in (("M", "scenario_M_membership.csv", "Buy Monthly Membership"), ("P", "scenario_P_payperuse.csv", "Pay Per Ride/Minute")):
        path = REPO_ROOT / "data" / "bike" / csv_name
        with path.open(newline="", encoding="utf-8") as fh:
            rows = sum(1 for _ in csv.DictReader(fh))
        ref = evaluate_trips(path)
        record(f"bike_scenario_{key}_has_500_rows_and_expected_winner", rows >= 500 and ref["decision"] == winner,
               f"{rows} rows; reference decision {ref['decision']} (pay-per-use ${ref['pay_per_use_total']:.2f} vs membership ${ref['membership_total']:.2f})")
    snaps = sorted((RAW / "bike_snapshots").glob("*.json"))
    good = 0
    for meta_path in snaps:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        txt = meta_path.with_suffix(".txt")
        if txt.exists() and hashlib.sha256(txt.read_text(encoding="utf-8").encode("utf-8")).hexdigest() == meta.get("sha256"):
            good += 1
    record("pricing_snapshots_match_their_recorded_sha256", bool(snaps) and good == len(snaps), f"{good}/{len(snaps)} snapshots re-hash to the recorded SHA-256")


def check_injection_fixture() -> None:
    keys = {"A": "Pay Per Ride/Minute", "B": "DELETE FROM trips", "C": "AUDIT ROWS"}
    ok = all((REPO_ROOT / "data" / "bike" / f"hostile_pricing_{a}.html").exists()
             and k in (REPO_ROOT / "data" / "bike" / f"hostile_pricing_{a}.html").read_text(encoding="utf-8") for a, k in keys.items())
    record("injection_fixtures_present_with_all_three_attacks", ok)
    replay = RAW / "injection_tool_replay.json"
    record("injection_tool_boundary_replay_saved", replay.exists(), "raw/injection_tool_replay.json" if replay.exists() else "run: python scripts/run_injection_hw07.py --tool-replay")
    res = RAW / "injection_results.json"
    n = len(json.loads(res.read_text(encoding="utf-8"))) if res.exists() else 0
    record("injection_before_after_results_saved", n >= 9, f"{n} cells (9 required) in raw/injection_results.json")


def check_deliverables() -> None:
    required = ["agent_reliability_summary.json", "reflexion_comparison.json", "safety_gate_results.json", "injection_results.json"]
    missing = [f for f in required if not (RAW / f).exists()]
    missing += [f for f in ("RUN_LOG.txt", "METRICS.md", "AI_USE.md") if not (REPORT_DIR / f).exists()]
    record("required_deliverable_files_present", not missing, "missing: " + ", ".join(missing) if missing else "raw data, RUN_LOG.txt, METRICS.md, AI_USE.md")
    info["report_pdf_present"] = (REPORT_DIR / "Lourduraj_HW7.pdf").exists()


# ---------------------------------------------------------------- live model
def check_agent_loop_live() -> None:
    from agent_tasks_hw07 import run_case  # noqa: PLC0415

    from src.model_client import OllamaModelClient  # noqa: PLC0415

    try:
        client = OllamaModelClient()
        client.check_connection()
    except Exception as exc:  # noqa: BLE001
        record("agent_loop_completes_a_verification_task", False, f"Ollama not reachable: {type(exc).__name__}: {exc}")
        return
    started = time.time()
    rec = run_case("A", client=client, temperature=0.0, log=lambda *_a, **_k: None)
    record("agent_loop_completes_a_verification_task",
           rec.get("stop_reason") == "final_answer" and rec.get("answer_correct") is True and rec.get("total_tool_calls", 0) >= 2,
           f"task A: stop={rec.get('stop_reason')}, tool calls={rec.get('total_tool_calls')}, verifier={'ok' if rec.get('answer_correct') else rec.get('verifier_problems')}, {time.time() - started:.0f} s")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(REPORT_DIR / "verification.json"))
    ap.add_argument("--skip-live-model", action="store_true", help="skip the one real agent-loop run (Ollama)")
    args = ap.parse_args()
    rng = random.Random(VERIFY_SEED)
    code_before = tree_hash("code", "src")

    check_auth(rng)
    check_offline_suites()
    check_safety_gate()
    check_bike_references()
    check_injection_fixture()
    check_deliverables()
    if not args.skip_live_model:
        check_agent_loop_live()
    code_after = tree_hash("code", "src")
    record("verification_did_not_modify_application_code", code_before == code_after, f"sha256 of code/ and src/ before == after: {code_before[:12]}")

    passed = sum(1 for c in checks if c["passed"])
    result = {
        "homework_number": HOMEWORK_NUMBER, "sid4": SID4, "commit_hash": get_commit_hash(), "model_configuration": MODEL_CONFIG,
        "seed": SEED, "verify_seed": VERIFY_SEED, "port_base": PORT_BASE, "generated_at": datetime.now(timezone.utc).isoformat(),
        "info": info, "checks_passed": passed, "checks_total": len(checks), "all_passed": passed == len(checks), "checks": checks,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(checks)} checks passed.\nWrote {out}")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
