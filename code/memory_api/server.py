"""HW6 Part 2 - wiring: attach the memory routes to the shared FastAPI app on PORT_BASE."""
from __future__ import annotations

import time

from fastapi import FastAPI

from .routes import router
from .store import init_memory_collections


def _startup_init_memory() -> None:
    last_err = None
    for _ in range(5):
        try:
            init_memory_collections()
            print("HW6 Part 2: memory collections ready (messages, summaries, episodes).")
            return
        except Exception as exc:  # noqa: BLE001 - retry any connection error
            last_err = exc
            time.sleep(2)
    print(f"HW6 Part 2 WARNING: could not initialise memory collections: {last_err}")


def install(app: FastAPI) -> None:
    app.include_router(router)
    app.on_event("startup")(_startup_init_memory)
