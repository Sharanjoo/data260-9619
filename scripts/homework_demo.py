"""HW8 Part 1 demonstration: the complete CREATE -> GET request/response flow over Kafka.

    python scripts/recorded_run_hw08.py -- python scripts/homework_demo.py [--errors] [--save]

Needs `docker compose up -d` (kafka, kafka-init, worker, web). The client here talks HTTP to the FastAPI wrapper
on PORT_BASE; the wrapper puts the request on s9619_entity_requests, the worker (separate container) answers on
s9619_entity_responses. The worker's and the API's own log lines for each correlation_id are read back with
`docker logs`, so one terminal shows send -> receive -> process -> reply -> client response in order.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import requests

REPO = Path(__file__).resolve().parent.parent
RAW = REPO / "reports/hw08/raw"
API = "http://127.0.0.1:8619/api/hw8"
PREFIX = "s9619"
REQUEST_TOPIC = f"{PREFIX}_entity_requests"
RESPONSE_TOPIC = f"{PREFIX}_entity_responses"
CONTAINERS = {"API": "data260-hw3-s9619", "WORKER": "data260-hw8-worker-s9619"}
BANNER = "Sharan Lourduraj | SID4 9619 | DATA 260 HW8 Part 1 (request/response over Kafka)"

NOTICE = {
    "productName": "Frozen Mixed Berries",
    "brandName": "Northfield Farms",
    "submitterEmail": "safety@northfield.example",
    "description": "Possible Hepatitis A contamination found in one lot; do not eat and return it to the store.",
    "category": "food-safety-recall",
    "termsAccepted": True,
}
LINE = re.compile(r"^(\d\d:\d\d:\d\d\.\d{3}) \[(API|WORKER)\] (.*)$")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def say(text: str) -> None:
    print(text, flush=True)


def container_lines(since_iso: str, cid: str) -> list:
    """Lines the API and the worker printed for this correlation_id, oldest first (read with `docker logs`)."""
    found = []
    for who, name in CONTAINERS.items():
        try:
            out = subprocess.run(["docker", "logs", "--since", since_iso, name], capture_output=True, text=True,
                                 encoding="utf-8", errors="replace", timeout=30)
        except (OSError, subprocess.TimeoutExpired) as exc:
            found.append(("00:00:00.000", f"[{who}] (could not read docker logs of {name}: {exc})"))
            continue
        for raw in (out.stdout + out.stderr).splitlines():
            m = LINE.match(raw.strip())
            if m and cid in raw:
                found.append((m.group(1), f"[{m.group(2)}] {m.group(3)}"))
    return sorted(found, key=lambda t: t[0])


def call(operation: str, data: dict, cid: str, step: str) -> dict:
    since = now_iso()
    request = {"operation": operation, "data": data, "correlation_id": cid}
    say(f"\n[CLIENT] {step}: send {operation} correlation_id={cid}")
    say(f"[CLIENT] POST {API}/requests -> the API wrapper puts it on topic {REQUEST_TOPIC}")
    say(f"[CLIENT] request body: {json.dumps(request)}")
    reply = requests.post(f"{API}/requests", json=request, timeout=60)
    body = reply.json()
    say(f"[CLIENT] response received: HTTP {reply.status_code} {json.dumps(body)}")
    say("[KAFKA FLOW] lines the API and the worker logged for this correlation_id (docker logs):")
    lines = container_lines(since, cid)
    for stamp, text in lines:
        say(f"    {stamp} {text}")
    if not lines:
        say("    (no lines found: is the stack running? try: docker logs data260-hw8-worker-s9619)")
    return {"request": request, "http_status": reply.status_code, "response": body,
            "flow_lines": [f"{s} {t}" for s, t in lines]}


def run_errors() -> list:
    say("\n=== extra: error responses also keep the correlation_id ===")
    results = []
    bad = {k: v for k, v in NOTICE.items() if k != "category"}
    for label, operation, data in (
            ("invalid CREATE (category missing)", "CREATE_RECALL_NOTICE", bad),
            ("GET with an unknown id", "GET_RECALL_NOTICE", {"recall_notice_id": str(uuid.uuid4())}),
            ("unknown operation", "DELETE_RECALL_NOTICE", {})):
        cid = str(uuid.uuid4())
        r = call(operation, data, cid, label)
        ok = r["response"].get("correlation_id") == cid and r["response"].get("success") is False
        say(f"[CLIENT] {label}: success=false and correlation_id preserved: {'YES' if ok else 'NO'}"
            f"  error={r['response'].get('error')!r}")
        results.append({"case": label, "ok": ok, **r})
    return results


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--errors", action="store_true", help="also show validation / not-found / unknown-operation replies")
    ap.add_argument("--save", action="store_true", help="write reports/hw08/raw/homework_demo.json")
    args = ap.parse_args()
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    say(BANNER)
    say(f"topics: {REQUEST_TOPIC} (requests), {RESPONSE_TOPIC} (responses)   API: {API}")
    try:
        requests.get(f"{API}/health", timeout=5).raise_for_status()
    except Exception as exc:  # noqa: BLE001
        say(f"cannot reach the API wrapper: {exc}\nstart it with: docker compose up -d")
        return 2

    create_cid = str(uuid.uuid4())
    say(f"\n1. created correlation_id for CREATE: {create_cid}")
    created = call("CREATE_RECALL_NOTICE", NOTICE, create_cid, "2-6. CREATE")
    body = created["response"]
    if not body.get("success"):
        say("CREATE failed, stopping.")
        return 1
    entity_id = body["recall_notice_id"]
    say(f"\n7. generated recall_notice_id extracted from the CREATE response: {entity_id}")

    get_cid = str(uuid.uuid4())
    say(f"\n8. new correlation_id for the GET request: {get_cid}")
    fetched = call("GET_RECALL_NOTICE", {"recall_notice_id": entity_id}, get_cid, "8-9. GET")
    reply = fetched["response"]
    say("\n10. retrieved recall notice:")
    say(json.dumps(reply.get("recall_notice"), indent=2))
    same_fields = all(reply.get("recall_notice", {}).get(k) == v for k, v in NOTICE.items())
    checks = {
        "CREATE succeeded and returned a UUID": bool(uuid.UUID(entity_id)),
        "CREATE response kept the correlation_id": body.get("correlation_id") == create_cid,
        "GET returned the same recall_notice_id": reply.get("recall_notice", {}).get("recall_notice_id") == entity_id,
        "GET returned the fields that were stored": same_fields,
        "GET response kept the correlation_id": reply.get("correlation_id") == get_cid,
    }
    for name, ok in checks.items():
        say(f"    [{'PASS' if ok else 'FAIL'}] {name}")
    extra = run_errors() if args.errors else []
    if args.save:
        RAW.mkdir(parents=True, exist_ok=True)
        (RAW / "homework_demo.json").write_text(json.dumps(
            {"created_at": now_iso(), "create": created, "get": fetched, "checks": checks, "errors": extra},
            indent=2), encoding="utf-8")
        say(f"\nsaved {RAW / 'homework_demo.json'}")
    return 0 if all(checks.values()) and all(e["ok"] for e in extra) else 1


if __name__ == "__main__":
    raise SystemExit(main())
