"""HW5 Part 3: timeout + bounded exponential-backoff retry policy, plus a
deterministic seeded fault-injection harness for stress-testing it.

Design
------
with_retry(operation, ...) wraps any zero-arg callable ("operation") that
may be slow or raise. Each attempt runs under a hard per-attempt timeout
(via concurrent.futures -- a hung/slow operation is actually cut off, not
just declared bounded in a docstring); a timeout or any other exception
from the operation counts as a failed attempt. Failed attempts are retried
up to max_retries additional times with exponential backoff
(base_delay_s * 2**attempt, capped at max_delay_s, +/-25% jitter) between
attempts. If every attempt fails, with_retry returns the same
{ok, data, error} envelope used throughout Part 2B/4 instead of raising --
"a clean error result instead of crashing," per the spec -- rather than
letting the final exception propagate.

FaultInjector deterministically decides, once per attempt, whether that
attempt should be forced to fail -- by sleeping past the per-attempt
timeout instead of calling through to the real operation, so with_retry's
own timeout enforcement is what actually catches it (a genuine timeout,
not a faked exception). Seeded with VERIFY_SEED (a fresh
random.Random(VERIFY_SEED) per failure-rate batch, see
scripts/fault_injection_hw05.py), so the same seed reproduces the
identical success/failure sequence on every run -- per the spec's "the
same seed must produce the same success/failure sequence each time."
"""
from __future__ import annotations

import random
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional

# 260000 + SID4(9619), per Section 0 of the HW5 spec.
VERIFY_SEED = 269619

_executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="retry-policy")


@dataclass
class RetryOutcome:
    """What with_retry() always returns -- never raises."""

    ok: bool
    data: Any
    error: Optional[str]
    attempts: int
    total_latency_ms: float
    attempt_latencies_ms: List[float] = field(default_factory=list)

    def envelope(self) -> dict:
        """The shared {ok, data, error} shape, for callers that just want
        that and not the retry/timing metadata."""
        return {"ok": self.ok, "data": self.data, "error": self.error}


def with_retry(
    operation: Callable[[], Any],
    *,
    max_retries: int = 3,
    timeout_s: float = 0.25,
    base_delay_s: float = 0.05,
    max_delay_s: float = 0.4,
    rng: Optional[random.Random] = None,
) -> RetryOutcome:
    """Run `operation` under a bounded exponential-backoff retry policy.

    Up to (1 + max_retries) total attempts, each bounded by timeout_s.
    Backoff between attempts is base_delay_s * 2**attempt, capped at
    max_delay_s, with +/-25% jitter so repeated failures don't retry in
    lockstep. `rng` controls the jitter (and is also what a fault
    injector's own fail/succeed decisions should share, for full
    reproducibility of both outcomes and timings given one seed).
    """
    rng = rng or random.Random()
    start = time.monotonic()
    attempt_latencies: List[float] = []
    last_error: Optional[str] = None

    for attempt in range(max_retries + 1):
        attempt_start = time.monotonic()
        future = _executor.submit(operation)
        try:
            result = future.result(timeout=timeout_s)
            attempt_latencies.append((time.monotonic() - attempt_start) * 1000)
            return RetryOutcome(
                ok=True,
                data=result,
                error=None,
                attempts=attempt + 1,
                total_latency_ms=(time.monotonic() - start) * 1000,
                attempt_latencies_ms=attempt_latencies,
            )
        except FutureTimeoutError:
            future.cancel()
            last_error = f"attempt {attempt + 1} timed out after {timeout_s}s"
        except Exception as exc:  # noqa: BLE001 -- any op failure retries the same way
            last_error = f"attempt {attempt + 1} failed: {exc}"
        attempt_latencies.append((time.monotonic() - attempt_start) * 1000)

        if attempt < max_retries:
            backoff = min(base_delay_s * (2**attempt), max_delay_s)
            jitter = backoff * rng.uniform(-0.25, 0.25)
            time.sleep(max(0.0, backoff + jitter))

    return RetryOutcome(
        ok=False,
        data=None,
        error=last_error or "all retry attempts failed",
        attempts=max_retries + 1,
        total_latency_ms=(time.monotonic() - start) * 1000,
        attempt_latencies_ms=attempt_latencies,
    )


def fault_wrapped(
    real_operation: Callable[[], Any],
    failure_rate: float,
    rng: random.Random,
    timeout_s: float,
) -> Callable[[], Any]:
    """Wrap `real_operation` so each *attempt* (this is re-invoked once per
    with_retry attempt, including retries) draws exactly one rng.random()
    to decide whether THIS attempt is forced to fail. A forced failure
    sleeps past timeout_s so with_retry's own timeout enforcement is what
    catches it -- a real timeout, not a simulated exception -- otherwise
    it calls through to the real operation. One draw per decision, in
    strict call order, is what makes the sequence reproducible for a given
    seed: see scripts/fault_injection_hw05.py.
    """

    def _call():
        if rng.random() < failure_rate:
            time.sleep(timeout_s + 0.05)
            return None  # unreachable: the caller's own timeout fires first
        return real_operation()

    return _call
