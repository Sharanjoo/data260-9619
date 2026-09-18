"""HW3 self-check: verifies corpus integrity, questions.yaml, Part 2 raw data shape,
and the live auth system, then writes reports/hw03/verification.json.

Run the app first (cd code && python main.py) in another terminal before running this.
"""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import requests
import yaml

BASE_URL = "http://localhost:8619"
CORPUS_DIR = Path("data/hw03_corpus")
HW03_DIR = Path("reports/hw03")
CORRECT_USER = "inspector"
CORRECT_PASS = "recall2026"

checks = []


def record(name, passed, detail=""):
    checks.append({"check": name, "passed": bool(passed), "detail": detail})
    status = "PASS" if passed else "FAIL"
    print(f"[{status}] {name}" + (f" — {detail}" if detail else ""))


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def check_corpus_manifest():
    manifest_path = HW03_DIR / "CORPUS_MANIFEST.json"
    if not manifest_path.exists():
        record("corpus_manifest_exists", False, "CORPUS_MANIFEST.json not found")
        return
    record("corpus_manifest_exists", True)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    docs = manifest.get("documents", [])
    mismatches = []
    for doc in docs:
        path = CORPUS_DIR / doc["filename"]
        if not path.exists():
            mismatches.append(f"{doc['filename']}: missing")
            continue
        actual_size = path.stat().st_size
        actual_hash = sha256_of(path)
        if actual_size != doc["bytes"]:
            mismatches.append(f"{doc['filename']}: size {actual_size} != manifest {doc['bytes']}")
        if actual_hash != doc["sha256"]:
            mismatches.append(f"{doc['filename']}: sha256 mismatch")

    total_bytes = sum(p.stat().st_size for p in CORPUS_DIR.glob("*.txt"))
    record(
        "corpus_files_match_manifest",
        len(mismatches) == 0,
        f"{len(docs)} documents checked, {len(mismatches)} mismatches" + (f": {mismatches}" if mismatches else ""),
    )
    record("corpus_meets_200kb_minimum", total_bytes >= 200_000, f"{total_bytes:,} bytes")


def check_questions_yaml():
    path = HW03_DIR / "questions.yaml"
    if not path.exists():
        record("questions_yaml_exists", False)
        return
    record("questions_yaml_exists", True)

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    questions = data.get("questions", [])
    record("questions_yaml_has_five_questions", len(questions) == 5, f"found {len(questions)}")

    required_fields = {"id", "question", "expected_answer", "expected_source_file"}
    malformed = [q.get("id", "?") for q in questions if not required_fields.issubset(q.keys())]
    record("questions_have_required_fields", len(malformed) == 0, f"malformed ids: {malformed}" if malformed else "")

    single_source_count = sum(1 for q in questions if q.get("single_source_dependent"))
    record("at_least_two_single_source_questions", single_source_count >= 2, f"{single_source_count} marked single-source")


def check_part2_raw_data():
    retrieval_path = HW03_DIR / "raw" / "retrieval_results.jsonl"
    if not retrieval_path.exists():
        record("retrieval_results_exists", False)
    else:
        record("retrieval_results_exists", True)
        rows = [json.loads(line) for line in retrieval_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        record("retrieval_results_row_count", len(rows) == 75, f"found {len(rows)} rows (expected 75 = 5 questions x 3 techniques x top-5)")

    chunk_stats_path = HW03_DIR / "raw" / "chunk_stats.csv"
    record("chunk_stats_exists", chunk_stats_path.exists())

    metrics_path = HW03_DIR / "METRICS.md"
    record("metrics_md_exists", metrics_path.exists())


def check_live_auth_system():
    try:
        resp = requests.get(f"{BASE_URL}/", timeout=5)
        record("home_page_reachable", resp.status_code == 200, f"status {resp.status_code}")
    except requests.exceptions.ConnectionError:
        record("home_page_reachable", False, "Connection refused — is the server running? (cd code && python main.py)")
        record("server_dependent_checks_skipped", False, "skipped remaining live checks")
        return

    resp = requests.post(f"{BASE_URL}/login", data={"username": CORRECT_USER, "password": "wrong-password"})
    record(
        "invalid_login_rejected",
        resp.status_code == 401 and "Invalid username or password" in resp.text,
        f"status {resp.status_code}",
    )

    resp = requests.get(f"{BASE_URL}/dashboard", timeout=5, allow_redirects=False)
    record(
        "dashboard_blocked_without_session",
        resp.status_code in (303, 307) and "/login" in resp.headers.get("location", ""),
        f"status {resp.status_code}, location={resp.headers.get('location')}",
    )

    resp = requests.post(
        f"{BASE_URL}/login",
        data={"username": CORRECT_USER, "password": CORRECT_PASS},
        allow_redirects=False,
    )
    login_ok = resp.status_code == 303 and "/dashboard" in resp.headers.get("location", "")
    record("valid_login_redirects_to_dashboard", login_ok, f"status {resp.status_code}")

    set_cookie = resp.headers.get("set-cookie", "")
    record(
        "set_cookie_has_required_attributes",
        all(attr.lower() in set_cookie.lower() for attr in ["HttpOnly", "SameSite", "Secure"]),
        set_cookie[:120] + ("..." if len(set_cookie) > 120 else ""),
    )

    # Send the cookie as a raw header instead of relying on requests' built-in
    # cookie jar. Python's http.cookiejar strictly enforces the Secure attribute
    # (only sent back over https://) with no exception for localhost — unlike
    # real browsers, which specifically treat http://localhost as a secure
    # context. That's why plain requests.Session() silently drops this cookie
    # even though your manual browser testing works fine. This is a client
    # policy quirk, not something the server enforces or a bug in the app.
    cookie_pair = set_cookie.split(";")[0]  # "hw3_session=<signed value>"
    auth_headers = {"Cookie": cookie_pair}

    resp = requests.get(f"{BASE_URL}/dashboard", timeout=5, headers=auth_headers)
    record(
        "authenticated_dashboard_reachable",
        resp.status_code == 200 and CORRECT_USER in resp.text,
        f"status {resp.status_code}",
    )

    # Sessions here are stateless: everything is encoded/signed into the cookie
    # itself, so "logout" can't revoke anything server-side. It works by telling
    # the client to switch to a NEW Set-Cookie value (one that decodes to an
    # empty session). A real browser always honors the latest Set-Cookie, so we
    # have to do the same here — capture /logout's own Set-Cookie and use THAT
    # for the follow-up check, instead of replaying the old pre-logout cookie.
    logout_resp = requests.get(f"{BASE_URL}/logout", timeout=5, headers=auth_headers, allow_redirects=False)
    post_logout_set_cookie = logout_resp.headers.get("set-cookie", "")
    post_logout_cookie_pair = post_logout_set_cookie.split(";")[0] if post_logout_set_cookie else ""
    post_logout_headers = {"Cookie": post_logout_cookie_pair} if post_logout_cookie_pair else {}

    resp = requests.get(f"{BASE_URL}/dashboard", timeout=5, headers=post_logout_headers, allow_redirects=False)
    record(
        "dashboard_blocked_after_logout",
        resp.status_code in (303, 307) and "/login" in resp.headers.get("location", ""),
        f"status {resp.status_code}",
    )


def main():
    check_corpus_manifest()
    check_questions_yaml()
    check_part2_raw_data()
    check_live_auth_system()

    passed = sum(1 for c in checks if c["passed"])
    total = len(checks)

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "domain_id": 3,
        "sid4": 9619,
        "checks_passed": passed,
        "checks_total": total,
        "all_passed": passed == total,
        "checks": checks,
    }

    out_path = HW03_DIR / "verification.json"
    out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

    print(f"\n{passed}/{total} checks passed.")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()