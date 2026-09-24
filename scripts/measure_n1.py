"""HW4 Part 3 steps 4-7: measure the naive (N+1) vs fixed (joinedload) list
endpoint at page sizes 10/50/200, 30 requests each (180 total), recording SQL
statement count per request (from the X-SQL-Query-Count response header set
by main.py's timing middleware) and client-observed latency.

Requires the app running and reachable (default http://localhost:8619) and
Part 3 seed data already loaded (scripts/seed_hw04.py).

Usage:
    python scripts/measure_n1.py
    python scripts/measure_n1.py --base-url http://localhost:8619
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

RAW_DIR = Path(__file__).resolve().parent.parent / "reports" / "hw04" / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

SESSION_COOKIE_NAME = "hw4_session"  # must match db_routes.py's SESSION_COOKIE_NAME
TEST_EMAIL = "loadtest@hw4demo.com"
TEST_PASSWORD = "loadtest2026"
TEST_NAME = "Load Tester"

PAGE_SIZES = [10, 50, 200]
VERSIONS = [("naive", "/api/hw4/records"), ("fixed", "/api/hw4/records-fixed")]
N_REQUESTS = 30
N_WARMUP = 2


def ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_auth_header(base_url: str) -> dict:
    """Log in and return a {"Cookie": "hw4_session=<token>"} header dict.

    db_routes.py sets the login cookie with Secure=True (needed so it works
    over http://localhost in a *browser*, which treats localhost as a secure
    context). Python's requests/http.cookiejar has no such exception and will
    silently refuse to resend a Secure cookie over plain http://, which makes
    every later request in a requests.Session come back 401 with no obvious
    cause. Rather than fight cookiejar's domain/secure matching rules, just
    read the token once and send it back as an explicit header on every
    request -- simple, and impossible to get wrong silently.
    """
    session = requests.Session()
    # Register (ignore 409 already-registered), then log in.
    session.post(
        f"{base_url}/api/hw4/auth/register",
        json={"name": TEST_NAME, "email": TEST_EMAIL, "password": TEST_PASSWORD},
        timeout=10,
    )
    resp = session.post(
        f"{base_url}/api/hw4/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        timeout=10,
    )
    resp.raise_for_status()

    token = resp.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        raise RuntimeError(
            f"Login succeeded (status {resp.status_code}) but no '{SESSION_COOKIE_NAME}' "
            f"cookie was found in the response -- check the cookie name in db_routes.py."
        )
    print(f"[measure_n1] {ts()} logged in as {TEST_EMAIL}")
    return {"Cookie": f"{SESSION_COOKIE_NAME}={token}"}


def percentile(values: list[float], p: float) -> float:
    if not values:
        return float("nan")
    k = (len(values) - 1) * (p / 100.0)
    f, c = int(k), min(int(k) + 1, len(values) - 1)
    sorted_vals = sorted(values)
    if f == c:
        return sorted_vals[f]
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


def run_one(base_url: str, path: str, page_size: int, headers: dict) -> dict:
    t0 = time.perf_counter()
    resp = requests.get(f"{base_url}{path}", params={"limit": page_size}, headers=headers, timeout=30)
    latency_ms = (time.perf_counter() - t0) * 1000.0
    if resp.status_code == 401:
        raise RuntimeError(
            f"401 Unauthorized on {path} even with an explicit Cookie header "
            f"({headers.get('Cookie', '')[:40]}...). The session token itself is "
            f"likely invalid/expired server-side -- try logging in fresh and re-running."
        )
    resp.raise_for_status()
    sql_count = int(resp.headers.get("X-SQL-Query-Count", "-1"))
    server_ms = float(resp.headers.get("X-Process-Time-Ms", "-1"))
    row_count = len(resp.json())
    return {
        "latency_ms": latency_ms,
        "server_process_ms": server_ms,
        "sql_query_count": sql_count,
        "row_count": row_count,
        "status_code": resp.status_code,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8619")
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")

    print(f"[measure_n1] {ts()} starting N+1 measurement against {base_url}")
    headers = get_auth_header(base_url)

    all_rows = []
    summary_rows = []

    for page_size in PAGE_SIZES:
        for version, path in VERSIONS:
            print(f"[measure_n1] {ts()} warming up {version} @ page_size={page_size} ...")
            for _ in range(N_WARMUP):
                run_one(base_url, path, page_size, headers)

            print(f"[measure_n1] {ts()} measuring {version} @ page_size={page_size} ({N_REQUESTS} requests)")
            measurements = []
            for i in range(N_REQUESTS):
                result = run_one(base_url, path, page_size, headers)
                measurements.append(result)
                all_rows.append({
                    "timestamp": ts(),
                    "page_size": page_size,
                    "version": version,
                    "request_index": i + 1,
                    **result,
                })

            latencies = [m["latency_ms"] for m in measurements]
            sql_counts = [m["sql_query_count"] for m in measurements]
            p50 = percentile(latencies, 50)
            p95 = percentile(latencies, 95)
            p99 = percentile(latencies, 99)
            sql_stmts = statistics.median(sql_counts)

            summary_rows.append({
                "page_size": page_size,
                "version": version,
                "sql_stmts_per_req": sql_stmts,
                "p50_ms": round(p50, 2),
                "p95_ms": round(p95, 2),
                "p99_ms": round(p99, 2),
            })
            print(
                f"[measure_n1]   -> sql_stmts/req={sql_stmts}  "
                f"p50={p50:.2f}ms  p95={p95:.2f}ms  p99={p99:.2f}ms"
            )

    raw_path = RAW_DIR / "n1_measurements.jsonl"
    with open(raw_path, "w", encoding="utf-8") as f:
        for row in all_rows:
            f.write(json.dumps(row) + "\n")
    print(f"[measure_n1] {ts()} wrote {len(all_rows)} raw rows to {raw_path}")

    summary_path = RAW_DIR / "n1_summary.csv"
    with open(summary_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["page_size", "version", "sql_stmts_per_req", "p50_ms", "p95_ms", "p99_ms"])
        writer.writeheader()
        writer.writerows(summary_rows)
    print(f"[measure_n1] {ts()} wrote summary table to {summary_path}")

    print("\n[measure_n1] === SUMMARY TABLE (paste into METRICS.md) ===")
    print(f"{'Page size':<12}{'Version':<10}{'SQL stmts/req':<16}{'p50 (ms)':<12}{'p95 (ms)':<12}{'p99 (ms)':<12}")
    for row in summary_rows:
        print(
            f"{row['page_size']:<12}{row['version']:<10}{row['sql_stmts_per_req']:<16}"
            f"{row['p50_ms']:<12}{row['p95_ms']:<12}{row['p99_ms']:<12}"
        )

    print(f"\n[measure_n1] {ts()} done. {len(all_rows)} total requests measured "
          f"({len(PAGE_SIZES)} page sizes x {len(VERSIONS)} versions x {N_REQUESTS} requests).")


if __name__ == "__main__":
    main()
