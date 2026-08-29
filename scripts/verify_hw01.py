"""Run Homework 1 basic checks and write reports/hw01/verification.json."""

from __future__ import annotations

import compileall
import json
import subprocess
import sys
import threading
import unittest
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = PROJECT_ROOT / "code/web_application"
OUTPUT_PATH = PROJECT_ROOT / "reports/hw01/verification.json"


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def run_tests() -> tuple[bool, int, int]:
    suite = unittest.defaultTestLoader.discover(str(PROJECT_ROOT / "tests"))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return result.wasSuccessful(), result.testsRun, len(result.failures) + len(result.errors)


def check_http_assets() -> dict[str, object]:
    handler = lambda *args, **kwargs: QuietHandler(  # noqa: E731
        *args,
        directory=str(WEB_ROOT),
        **kwargs,
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    statuses: dict[str, int] = {}
    try:
        port = server.server_address[1]
        for asset in ("index.html", "styles.css", "app.js"):
            with urlopen(f"http://127.0.0.1:{port}/{asset}", timeout=5) as response:
                response.read()
                statuses[asset] = response.status
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    return {"passed": all(status == 200 for status in statuses.values()), "statuses": statuses}


def git_commit() -> str | None:
    process = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=PROJECT_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return process.stdout.strip() if process.returncode == 0 else None


def external_evidence() -> dict[str, object]:
    screenshots = PROJECT_ROOT / "reports/hw01/screenshots"
    expected = [
        "01_web_form.png",
        "02_js_console.png",
        "03_docker_localhost.png",
        "04_agents_console.png",
        "05_client_stats_turn3.png",
        "06_client_stats_turn5.png",
        "07_nondeterminism_complete.png",
        "08_aws_ecs_service.png",
        "09_aws_public_ip.png",
    ]
    present = [name for name in expected if (screenshots / name).is_file()]
    raw = PROJECT_ROOT / "reports/hw01/raw"
    required_raw = [
        "agent_demo_result.json",
        "client_token_counts.json",
        "nondeterminism_results.json",
        "nondeterminism_results.csv",
    ]
    raw_present = [name for name in required_raw if (raw / name).is_file()]
    return {
        "screenshots_present": present,
        "screenshots_missing": [name for name in expected if name not in present],
        "raw_results_present": raw_present,
        "raw_results_missing": [name for name in required_raw if name not in raw_present],
        "complete": len(present) == len(expected) and len(raw_present) == len(required_raw),
    }


def check_shared_code_layout() -> dict[str, object]:
    legacy_root_files = [
        "index.html",
        "styles.css",
        "app.js",
        "agents_demo.py",
        "hw1_client.py",
        "Dockerfile",
    ]
    legacy_present = [path for path in legacy_root_files if (PROJECT_ROOT / path).exists()]
    reports_root = PROJECT_ROOT / "reports"
    application_suffixes = {".py", ".js", ".html", ".css"}
    code_in_reports = [
        str(path.relative_to(PROJECT_ROOT))
        for path in reports_root.rglob("*")
        if path.is_file() and path.suffix.lower() in application_suffixes
    ]
    return {
        "passed": not legacy_present and not code_in_reports,
        "legacy_root_files_present": legacy_present,
        "application_code_under_reports": code_in_reports,
    }


def main() -> int:
    required = [
        "README.md",
        "DOMAIN_SCHEMA.md",
        "code/web_application/index.html",
        "code/web_application/styles.css",
        "code/web_application/app.js",
        "code/Dockerfile",
        "compose.yaml",
        "code/agents_demo.py",
        "AGENT.md",
        "src/model_client.py",
        "code/hw1_client.py",
        "reports/hw01/RUN_LOG.txt",
        "reports/hw01/METRICS.md",
        "reports/hw01/AI_USE.md",
        "reports/hw01/reproducible_run_instructions.md",
        "reports/hw01/cases/nondeterminism_input.json",
    ]
    missing = [path for path in required if not (PROJECT_ROOT / path).is_file()]
    compiled = compileall.compile_dir(PROJECT_ROOT, quiet=1)
    tests_passed, tests_run, test_failures = run_tests()
    http = check_http_assets()
    shared_code_layout = check_shared_code_layout()
    evidence = external_evidence()
    basic_passed = (
        not missing
        and compiled
        and tests_passed
        and bool(http["passed"])
        and bool(shared_code_layout["passed"])
    )

    payload = {
        "generated_at_utc": utc_now(),
        "sid4": 9619,
        "configuration": {
            "port_base": 8000 + (9619 % 900),
            "prefix": "s9619",
            "seed": 9619,
            "verify_seed": 260000 + 9619,
            "domain_id": 9619 % 8,
        },
        "git_commit": git_commit(),
        "checks": {
            "required_files": {"passed": not missing, "missing": missing},
            "python_compile": {"passed": compiled},
            "unit_tests": {
                "passed": tests_passed,
                "tests_run": tests_run,
                "failures_and_errors": test_failures,
            },
            "local_http_assets": http,
            "shared_code_layout": shared_code_layout,
        },
        "external_evidence": evidence,
        "basic_checks_passed": basic_passed,
        "submission_ready": basic_passed and bool(evidence["complete"]),
        "note": (
            "Basic checks do not replace the required real Docker, Ollama, 40-run, and AWS evidence."
        ),
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    print(f"Wrote {OUTPUT_PATH.relative_to(PROJECT_ROOT)}")
    return 0 if basic_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
