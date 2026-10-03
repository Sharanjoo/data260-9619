"""HW5 Part 3.19: demonstrate the three required retry-policy scenarios.

Runs against small purpose-built fake operations (not the live database),
so each scenario is exact and reproducible on demand -- this is what you
screenshot for the report (one screenshot of this terminal output covers
all three required scenarios: the heading for each is printed clearly).

The larger probabilistic 150-call fault-injection experiment (Part 3.20) is
a separate script: scripts/fault_injection_hw05.py.

Usage (from the repo root, no DB/network needed):
    python scripts/demo_retry_scenarios_hw05.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "mcp_servers"))

from retry_policy import with_retry  # noqa: E402


def scenario_success_first_attempt() -> None:
    print("=== Scenario 1: success on the first attempt ===")
    outcome = with_retry(lambda: "fetched on first try")
    print(f"ok={outcome.ok}  attempts={outcome.attempts}  "
          f"total_latency_ms={outcome.total_latency_ms:.1f}")
    print(f"data={outcome.data!r}")
    assert outcome.ok and outcome.attempts == 1
    print("PASS\n")


def scenario_fail_then_succeed() -> None:
    print("=== Scenario 2: fail on attempt 1, succeed on attempt 2 ===")
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] == 1:
            raise ConnectionError("simulated transient failure on attempt 1")
        return "fetched on attempt 2"

    outcome = with_retry(flaky, max_retries=3)
    print(f"ok={outcome.ok}  attempts={outcome.attempts}  "
          f"total_latency_ms={outcome.total_latency_ms:.1f}")
    print(f"data={outcome.data!r}")
    assert outcome.ok and outcome.attempts == 2
    print("PASS\n")


def scenario_fail_all_retries() -> None:
    print("=== Scenario 3: fail on every attempt -> clean error, no crash ===")

    def always_fails():
        raise ConnectionError("simulated permanent failure")

    outcome = with_retry(always_fails, max_retries=3)
    print(f"ok={outcome.ok}  attempts={outcome.attempts}  "
          f"total_latency_ms={outcome.total_latency_ms:.1f}")
    print(f"error={outcome.error!r}")
    assert not outcome.ok and outcome.attempts == 4 and outcome.error
    print("PASS\n")


if __name__ == "__main__":
    scenario_success_first_attempt()
    scenario_fail_then_succeed()
    scenario_fail_all_retries()
    print("All three required Part 3.19 scenarios demonstrated successfully.")
