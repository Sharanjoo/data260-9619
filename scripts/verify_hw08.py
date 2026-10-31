"""HW8 self-check (make verify-hw08): a smoke test of the Kafka request/response service plus the saved evidence.

Live checks (need `docker compose up -d`: kafka, kafka-init, worker and the FastAPI backend on PORT_BASE):
  GET /api/hw8/health, CREATE_RECALL_NOTICE then GET_RECALL_NOTICE round trip through the two Kafka topics (the
  correlation_id must come back unchanged, the stored fields must match), an invalid create (422) and an unknown id
  (404) that also keep their correlation_id, and the seven topics with s9619_tasks having 2 partitions.
Offline checks: both test suites (test_kafka_hw08.py, test_agents_hw08.py), the saved Part 2 journey (approved, same
correlation_id in every stage log) and the saved Part 3 results (each failure shows the expected before/after
behaviour), and the required deliverable files.
It does NOT modify application code: it hashes code/ and src/ before and after and records the result as a check.
The Part 3 failure tests themselves are long (several minutes), so they are run by scripts/part3_hw08.py, not here.

Usage (repo root):   python scripts/verify_hw08.py            (writes reports/hw08/verification.json)
                     python scripts/verify_hw08.py --skip-live
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
REPORT_DIR = REPO_ROOT / "reports" / "hw08"
RAW = REPORT_DIR / "raw"
sys.path.insert(0, str(REPO_ROOT / "code"))

from kafka_agents.settings import (DEAD_LETTER_TOPIC, DRAFTS_TOPIC, FINAL_TOPIC, INBOX_TOPIC, TASKS_PARTITIONS,  # noqa: E402
                                   TASKS_TOPIC)
from kafka_api.config import BOOTSTRAP_SERVERS, PORT_BASE, REQUEST_TOPIC, RESPONSE_TOPIC, SEED, SID4, VERIFY_SEED  # noqa: E402

BASE_URL = f"http://127.0.0.1:{PORT_BASE}/api/hw8"
HOMEWORK_NUMBER = 8
MODEL_CONFIG = ("Part 2 journey: qwen3:8b via Ollama (HW1 adapter, temperature 0, think off); Part 3 failure tests: the "
                "same agents in deterministic fast mode (no model call). Kafka: apache/kafka:3.9.2 single-node KRaft, "
                "aiokafka client, manual offset commit after processing, 2-partition task topic")
GOOD = {"productName": "Frozen Mixed Berries", "brandName": "Northfield Farms", "submitterEmail": "safety@northfield.example",
        "description": "Possible Hepatitis A contamination found in one lot; do not eat and return it to the store.",
        "category": "food-safety-recall", "termsAccepted": True}

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


def load(name: str):
    path = RAW / name
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def valid_uuid(value: object) -> bool:
    try:
        return str(uuid.UUID(str(value))) == str(value)
    except ValueError:
        return False


# ---------------------------------------------------------------- live: Kafka request/response service
def check_round_trip() -> None:
    try:
        health = requests.get(f"{BASE_URL}/health", timeout=15)
    except requests.RequestException as exc:
        record("backend_reachable", False, f"{type(exc).__name__} on {BASE_URL} (docker compose up -d)")
        return
    record("backend_reachable", health.status_code == 200, f"GET {BASE_URL}/health -> HTTP {health.status_code}")

    create_cid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"s9619-verify-{VERIFY_SEED}-create-{uuid.uuid4()}"))
    r = requests.post(f"{BASE_URL}/requests", json={"operation": "CREATE_RECALL_NOTICE", "data": GOOD,
                                                    "correlation_id": create_cid}, timeout=30)
    body = r.json()
    notice_id = body.get("recall_notice_id")
    record("create_goes_through_kafka_and_returns_uuid", r.status_code == 201 and body.get("success") is True and valid_uuid(notice_id),
           f"HTTP {r.status_code}, recall_notice_id={notice_id}")
    record("create_response_keeps_correlation_id", body.get("correlation_id") == create_cid, f"sent {create_cid}, got {body.get('correlation_id')}")

    get_cid = str(uuid.uuid4())
    g = requests.post(f"{BASE_URL}/requests", json={"operation": "GET_RECALL_NOTICE", "data": {"recall_notice_id": notice_id},
                                                    "correlation_id": get_cid}, timeout=30)
    gb = g.json()
    notice = gb.get("recall_notice") or {}
    same = all(notice.get(k) == v for k, v in GOOD.items()) and notice.get("recall_notice_id") == notice_id
    record("get_returns_the_stored_notice", g.status_code == 200 and gb.get("success") is True and same, f"HTTP {g.status_code}")
    record("get_response_keeps_correlation_id", gb.get("correlation_id") == get_cid, f"sent {get_cid}, got {gb.get('correlation_id')}")

    bad_cid = str(uuid.uuid4())
    bad = requests.post(f"{BASE_URL}/requests", json={"operation": "CREATE_RECALL_NOTICE", "correlation_id": bad_cid,
                                                      "data": {k: v for k, v in GOOD.items() if k != "category"}}, timeout=30)
    bb = bad.json()
    record("invalid_create_rejected_with_correlation_id", bad.status_code == 422 and bb.get("success") is False and bb.get("correlation_id") == bad_cid,
           f"HTTP {bad.status_code}, error={bb.get('error')}")
    miss_cid = str(uuid.uuid4())
    miss = requests.post(f"{BASE_URL}/requests", json={"operation": "GET_RECALL_NOTICE", "correlation_id": miss_cid,
                                                       "data": {"recall_notice_id": str(uuid.uuid4())}}, timeout=30)
    mb = miss.json()
    record("unknown_id_returns_not_found_with_correlation_id", miss.status_code == 404 and mb.get("error") == "Recall notice not found"
           and mb.get("correlation_id") == miss_cid, f"HTTP {miss.status_code}, error={mb.get('error')}")
    unk_cid = str(uuid.uuid4())
    unk = requests.post(f"{BASE_URL}/requests", json={"operation": "DELETE_RECALL_NOTICE", "correlation_id": unk_cid, "data": {}}, timeout=30)
    ub = unk.json()
    record("unknown_operation_rejected_with_correlation_id", ub.get("success") is False and ub.get("error") == "Unknown operation"
           and ub.get("correlation_id") == unk_cid, f"HTTP {unk.status_code}, error={ub.get('error')}")


async def _topics() -> tuple:
    from aiokafka.admin import AIOKafkaAdminClient  # noqa: PLC0415

    admin = AIOKafkaAdminClient(bootstrap_servers=BOOTSTRAP_SERVERS)
    await admin.start()
    try:
        names = set(await admin.list_topics())
        described = await admin.describe_topics(sorted(n for n in names if n.startswith("s9619_")))
        return names, {(d.get("topic") or d.get("name")): len(d["partitions"]) for d in described}
    finally:
        await admin.close()


def check_topics() -> None:
    try:
        names, parts = asyncio.run(_topics())
    except Exception as exc:  # noqa: BLE001
        record("kafka_topics_exist", False, f"{type(exc).__name__}: {exc} (broker {BOOTSTRAP_SERVERS})")
        return
    need = [REQUEST_TOPIC, RESPONSE_TOPIC, INBOX_TOPIC, TASKS_TOPIC, DRAFTS_TOPIC, FINAL_TOPIC, DEAD_LETTER_TOPIC]
    missing = [t for t in need if t not in names]
    record("kafka_topics_exist", not missing, "all 7 topics present" if not missing else "missing: " + ", ".join(missing))
    record("entity_service_uses_exactly_two_topics_and_tasks_has_two_partitions",
           parts.get(TASKS_TOPIC) == TASKS_PARTITIONS and parts.get(REQUEST_TOPIC) == 1 and parts.get(RESPONSE_TOPIC) == 1,
           f"{TASKS_TOPIC}: {parts.get(TASKS_TOPIC)} partitions")


# ---------------------------------------------------------------- offline
def check_suites() -> None:
    for script in ("test_kafka_hw08.py", "test_agents_hw08.py"):
        try:
            p = subprocess.run([sys.executable, str(REPO_ROOT / "scripts" / script)], cwd=REPO_ROOT, capture_output=True, text=True, timeout=900)
            lines = [ln for ln in p.stdout.strip().splitlines() if ln.strip()]
            last = lines[-1] if lines else "no output"
            record(f"suite_{script.replace('.py', '')}", p.returncode == 0 and "checks passed" in last and " 0 failed" in last, last)
        except Exception as exc:  # noqa: BLE001
            record(f"suite_{script.replace('.py', '')}", False, f"{type(exc).__name__}: {exc}")


def check_part1_demo() -> None:
    demo = load("homework_demo.json")
    record("part1_demo_run_saved", demo is not None, "raw/homework_demo.json" if demo else "run: python scripts/recorded_run_hw08.py -- python scripts/homework_demo.py --errors --save")


def check_part2_journey() -> None:
    final = load("part2_final.json")
    log = RAW / "part2_journey.log"
    if final is None or not log.exists():
        record("part2_journey_saved", False, "raw/part2_final.json and raw/part2_journey.log")
        return
    cid = final.get("correlation_id", "")
    text = log.read_text(encoding="utf-8")
    stages = {s: any(cid in ln and f"[{s}" in ln for ln in text.splitlines()) for s in ("PLANNER", "WRITER", "REVIEWER", "CLIENT")}
    record("part2_final_message_approved_with_answer", final.get("status") == "approved" and bool(final.get("answer")), f"status={final.get('status')}")
    record("part2_correlation_id_in_every_stage_log", all(stages.values()), f"{cid[:8]}...: " + ", ".join(f"{k}={'yes' if v else 'no'}" for k, v in stages.items()))


def check_part3_results() -> None:
    expected = {
        "duplicate": lambda b, a: b["counts"][DRAFTS_TOPIC] >= 2 and a["counts"][DRAFTS_TOPIC] == 1 and a["counts"][FINAL_TOPIC] == 1,
        "kill": lambda b, a: b["drafts_after_restart"] == 0 and a["drafts_after_restart"] == 1,
        "poison": lambda b, a: b["good_messages_processed"] == 0 and a["failed_attempts_logged"] == 3 and a["dead_letter_copies"] == 1
        and a["good_messages_processed"] == 2,
        "ordering": lambda b, a: b["ordering"]["total_out_of_order_pairs"] > 0 and a["ordering"]["total_out_of_order_pairs"] == 0
        and not a["entities_split_over_partitions"] and a["processed"] == 20,
    }
    for name, rule in expected.items():
        data = load(f"part3_{name}.json")
        if data is None:
            record(f"part3_{name}_before_and_after", False, f"raw/part3_{name}.json missing (python scripts/part3_hw08.py {name})")
            continue
        v = data["variants"]
        try:
            ok = "before" in v and "after" in v and bool(v["before"].get("as_expected")) and bool(v["after"].get("as_expected")) and rule(v["before"], v["after"])
        except (KeyError, TypeError):
            ok = False
        record(f"part3_{name}_before_shows_the_failure_after_shows_the_fix", ok, "saved by scripts/part3_hw08.py")


def check_deliverables() -> None:
    missing = [f for f in ("RUN_LOG.txt", "METRICS.md", "AI_USE.md") if not (REPORT_DIR / f).exists()]
    record("required_deliverable_files_present", not missing, "missing: " + ", ".join(missing) if missing else "RUN_LOG.txt, METRICS.md, AI_USE.md, raw/")
    info["report_pdf_present"] = (REPORT_DIR / "Lourduraj_HW8.pdf").exists()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(REPORT_DIR / "verification.json"))
    ap.add_argument("--skip-live", action="store_true", help="skip the checks that need docker compose / Kafka")
    args = ap.parse_args()
    code_before = tree_hash("code", "src")
    if not args.skip_live:
        check_round_trip()
        check_topics()
    check_suites()
    check_part1_demo()
    check_part2_journey()
    check_part3_results()
    check_deliverables()
    code_after = tree_hash("code", "src")
    record("verification_did_not_modify_application_code", code_before == code_after, f"sha256 of code/ and src/ before == after: {code_before[:12]}")

    passed = sum(1 for c in checks if c["passed"])
    try:
        import aiokafka  # noqa: PLC0415
        info["aiokafka"] = aiokafka.__version__
    except ImportError:
        info["aiokafka"] = "not installed"
    info.update({"kafka_image": "apache/kafka:3.9.2", "bootstrap_servers_from_host": BOOTSTRAP_SERVERS, "live_checks_skipped": args.skip_live})
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
