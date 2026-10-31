"""One-line log helper: every component prints '<UTC time> [COMPONENT] text' and flushes at once,
so `docker logs` and the terminal show the lines in the order they happened."""
from __future__ import annotations

import sys
from datetime import datetime, timezone


def log(component: str, text: str) -> None:
    stamp = datetime.now(timezone.utc).strftime("%H:%M:%S.%f")[:-3]
    print(f"{stamp} [{component}] {text}", file=sys.stdout, flush=True)
