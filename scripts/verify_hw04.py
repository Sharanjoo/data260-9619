"""HW4 self-check: smoke-tests the live backend, the Part 3 seed data, and the
Part 4 RAG raw outputs, then writes reports/hw04/verification.json.

Run the app first (docker compose up -d) before running this. Does not modify
any application code; only reads the live API and the repo's own output files.

Usage:
    python scripts/verify_hw04.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "code"))

import os  # noqa: E402

# db.py connects to MySQL directly (bypassing the app container, which already
# uses the Docker-internal port). When this script runs standalone on the host,
# it needs the *host-mapped* MySQL port from compose.yaml (43306, not the
# container-internal 3306) -- setdefault so an explicitly-set env var still wins,
# but nobody running this cold (including a grader) needs to know that detail.
os.environ.setdefault("MYSQL_HOST", "127.0.0.1")
os.environ.setdefault("MYSQL_PORT", "43306")
os.environ.setdefault("MYSQL_USER", "hw4_user")
os.environ.setdefault("MYSQL_PASSWORD", "hw4_pass_9619")
os.environ.setdefault("MYSQL_DB", "s9619_rel")

BASE_URL = "http://localhost:8619"
OLLAMA_URL = "http://localhost:11434"

HOMEWORK_NUMBER = 4
SID4 = 9619
PORT_BASE = 8619
SEED = 9619
VERIFY_SEED = 269619
MODEL_CONFIG = "qwen3:8b via Ollama (Part 4); sentence-transformers/all-MiniLM-L6-v2 (embeddings, Part 4)"

VERIFY_EMAIL = "verify_hw04@hw4demo.com"
VERIFY_PASSWORD = "verify2026"
SESSION_COOKIE_NAME = "hw4_session"

checks: list[dict] = []


def record(name: str, passed: bool, detail: str = "") -> None:
    checks.append({"check": name, "passed": bool(passed), "detail": detail})
    status = "PASS" if passed else "FAIL"
    print(f"[{status}] {name}" + (f" -- {detail}" if detail else ""))


def get_commit_hash() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        return "unknown (not a git checkout, or git unavailable)"


def check_backend_health() -> None:
    try:
        resp = requests.get(f"{BASE_URL}/api/health", timeout=5)
        record(
            "backend_responds_on_port_base",
            resp.status_code == 200 and resp.json().get("port") == PORT_BASE,
            f"status={resp.status_code}, body={resp.text[:120]}",
        )
    except requests.exceptions.ConnectionError:
        record("backend_responds_on_port_base", False, f"Connection refused on {BASE_URL} -- is docker compose up?")


def get_authenticated_cookie_header() -> dict | None:
    try:
        requests.post(
            f"{BASE_URL}/api/hw4/auth/register",
            json={"name": "Verify Script", "email": VERIFY_EMAIL, "password": VERIFY_PASSWORD},
            timeout=10,
        )
        resp = requests.post(
            f"{BASE_URL}/api/hw4/auth/login",
            json={"email": VERIFY_EMAIL, "password": VERIFY_PASSWORD},
            timeout=10,
        )
        resp.raise_for_status()
        token = resp.cookies.get(SESSION_COOKIE_NAME)
        record("login_issues_session_cookie", bool(token), f"cookie name={SESSION_COOKIE_NAME}")
        if not token:
            return None
        return {"Cookie": f"{SESSION_COOKIE_NAME}={token}"}
    except Exception as exc:
        record("login_issues_session_cookie", False, str(exc))
        return None


def check_unauthenticated_blocked() -> None:
    try:
        resp = requests.get(f"{BASE_URL}/api/hw4/records", timeout=5)
        record("unauthenticated_records_request_blocked", resp.status_code == 401, f"status={resp.status_code}")
    except Exception as exc:
        record("unauthenticated_records_request_blocked", False, str(exc))


def check_naive_and_fixed_both_return_data(headers: dict) -> None:
    try:
        naive = requests.get(f"{BASE_URL}/api/hw4/records", params={"limit": 5}, headers=headers, timeout=10)
        fixed = requests.get(f"{BASE_URL}/api/hw4/records-fixed", params={"limit": 5}, headers=headers, timeout=10)
        naive_ok = naive.status_code == 200 and len(naive.json()) > 0
        fixed_ok = fixed.status_code == 200 and len(fixed.json()) > 0
        record("naive_list_endpoint_returns_data", naive_ok, f"status={naive.status_code}, rows={len(naive.json()) if naive_ok else '?'}")
        record("fixed_list_endpoint_returns_data", fixed_ok, f"status={fixed.status_code}, rows={len(fixed.json()) if fixed_ok else '?'}")

        naive_sql = int(naive.headers.get("X-SQL-Query-Count", "-1"))
        fixed_sql = int(fixed.headers.get("X-SQL-Query-Count", "-1"))
        record(
            "fixed_endpoint_uses_fewer_or_equal_sql_statements_than_naive",
            0 <= fixed_sql <= naive_sql,
            f"naive={naive_sql} queries, fixed={fixed_sql} queries",
        )
    except Exception as exc:
        record("naive_list_endpoint_returns_data", False, str(exc))
        record("fixed_list_endpoint_returns_data", False, str(exc))


def check_seed_data_present() -> None:
    try:
        from db import RecallRecord, RecallSource, db_session_basede26  # noqa: E402

        db = db_session_basede26()
        try:
            record_count = db.query(RecallRecord).count()
            source_count = db.query(RecallSource).count()
            record("part3_seed_5000_recall_records", record_count >= 5000, f"found {record_count} rows")
            record("part3_seed_200_recall_sources", source_count >= 200, f"found {source_count} rows")
        finally:
            db.close()
    except Exception as exc:
        record("part3_seed_5000_recall_records", False, f"could not query MySQL directly: {exc}")
        record("part3_seed_200_recall_sources", False, f"could not query MySQL directly: {exc}")


def check_index_added() -> None:
    try:
        from sqlalchemy import text  # noqa: E402
        from db import engine  # noqa: E402

        with engine.connect() as conn:
            result = conn.execute(
                text(
                    "SELECT COUNT(*) FROM information_schema.statistics "
                    "WHERE table_schema = DATABASE() AND table_name = 'recall_record' "
                    "AND index_name = 'idx_recall_record_product_name'"
                )
            )
            exists = result.scalar() > 0
        record("part3_index_created", exists, "idx_recall_record_product_name on recall_record.product_name")
    except Exception as exc:
        record("part3_index_created", False, str(exc))


def check_ollama_reachable() -> None:
    try:
        resp = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        record("ollama_reachable", resp.status_code == 200, f"status={resp.status_code}")
    except Exception as exc:
        record("ollama_reachable", False, f"Cannot reach Ollama at {OLLAMA_URL}: {exc}")


def check_part3_raw_files() -> None:
    raw_dir = REPO_ROOT / "reports" / "hw04" / "raw"
    n1_path = raw_dir / "n1_measurements.jsonl"
    explain_path = raw_dir / "explain_before_after.json"

    if n1_path.exists():
        row_count = sum(1 for line in n1_path.read_text(encoding="utf-8").splitlines() if line.strip())
        record("part3_n1_raw_data_180_rows", row_count == 180, f"found {row_count} rows (expected 180 = 3 page sizes x 2 versions x 30 requests)")
    else:
        record("part3_n1_raw_data_180_rows", False, f"{n1_path} not found")

    record("part3_explain_before_after_exists", explain_path.exists(), str(explain_path))


def check_part4_raw_files() -> None:
    raw_dir = REPO_ROOT / "reports" / "hw04" / "raw"
    results_path = raw_dir / "rag_question_results.jsonl"
    sweep_path = raw_dir / "rag_k_sweep.json"
    eval_path = raw_dir / "rag_eval_table.csv"

    if results_path.exists():
        rows = [json.loads(line) for line in results_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        record("part4_six_questions_answered", len(rows) == 6, f"found {len(rows)} question results (expected 6)")
        refused_q5_q6 = all(
            r["refused_config_c"] for r in rows if r["id"] in ("Q5", "Q6")
        ) if rows else False
        record("part4_q5_q6_refused_under_context_engineered_config", refused_q5_q6, "checked answer_context_engineered for Q5/Q6")
    else:
        record("part4_six_questions_answered", False, f"{results_path} not found")
        record("part4_q5_q6_refused_under_context_engineered_config", False, f"{results_path} not found")

    if sweep_path.exists():
        sweep = json.loads(sweep_path.read_text(encoding="utf-8"))
        record("part4_k_sweep_three_values", len(sweep) == 3, f"found {len(sweep)} k values (expected 3: k=1,3,5)")
    else:
        record("part4_k_sweep_three_values", False, f"{sweep_path} not found")

    record("part4_eval_table_exists", eval_path.exists(), str(eval_path))


def check_react_client_files_exist() -> None:
    client_dir = REPO_ROOT / "client" / "src" / "components"
    required = ["Login.jsx", "Home.jsx", "CreateRecord.jsx", "UpdateRecord.jsx", "DeleteRecord.jsx"]
    missing = [name for name in required if not (client_dir / name).exists()]
    record("part1_five_required_components_exist", len(missing) == 0, f"missing: {missing}" if missing else "all present")


def main() -> None:
    print(f"[verify_hw04] SID4={SID4}  commit={get_commit_hash()}")

    check_react_client_files_exist()
    check_backend_health()
    headers = get_authenticated_cookie_header()
    check_unauthenticated_blocked()
    if headers:
        check_naive_and_fixed_both_return_data(headers)
    else:
        record("naive_list_endpoint_returns_data", False, "skipped -- login failed")
        record("fixed_list_endpoint_returns_data", False, "skipped -- login failed")
        record("fixed_endpoint_uses_fewer_or_equal_sql_statements_than_naive", False, "skipped -- login failed")
    check_seed_data_present()
    check_index_added()
    check_part3_raw_files()
    check_ollama_reachable()
    check_part4_raw_files()

    passed = sum(1 for c in checks if c["passed"])
    total = len(checks)

    result = {
        "homework_number": HOMEWORK_NUMBER,
        "sid4": SID4,
        "commit_hash": get_commit_hash(),
        "model_configuration": MODEL_CONFIG,
        "seed": SEED,
        "verify_seed": VERIFY_SEED,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "checks_passed": passed,
        "checks_total": total,
        "all_passed": passed == total,
        "checks": checks,
    }

    out_path = REPO_ROOT / "reports" / "hw04" / "verification.json"
    out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

    print(f"\n{passed}/{total} checks passed.")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
