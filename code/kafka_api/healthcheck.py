"""HW8 - Docker health check for the worker: healthy while its heartbeat file was touched in the last 30 s.

The web image's own HEALTHCHECK asks port 8619 for /api/health, which the worker does not serve, so the
worker gets this check instead (compose.yaml: worker -> healthcheck).   python -m kafka_api.healthcheck
"""
from __future__ import annotations

import os
import sys
import tempfile
import time

HEARTBEAT_FILE = os.path.join(tempfile.gettempdir(), "hw8_worker_alive")
MAX_AGE_S = 30.0


def healthy(path: str = HEARTBEAT_FILE, now: float | None = None) -> bool:
    try:
        return (now if now is not None else time.time()) - os.path.getmtime(path) < MAX_AGE_S
    except OSError:
        return False


if __name__ == "__main__":
    sys.exit(0 if healthy() else 1)
