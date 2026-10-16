"""HW6 Part 1 - server configuration: how the document API is wired into FastAPI.

`install(app)` is what code/main.py calls so the HW6 routes share the one
FastAPI server on PORT_BASE (8619). `create_app()` builds a standalone app
(CORS middleware + JSON body parsing + the same routes) for tests or for running
Part 1 on its own:

    python -m doc_api.server        # from the code/ folder
"""
from __future__ import annotations

import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import CORS_ORIGINS, PORT_BASE
from .errors import register_error_handlers
from .mongo import init_notices_collection
from .routes import router


def _startup_init_mongo() -> None:
    """Create the collection/validator/indexes. MongoDB's container can start a
    few seconds after the app, so retry briefly; never crash the whole app (HW5's
    MySQL routes must keep working) if MongoDB is simply not running."""
    last_err = None
    for _ in range(5):
        try:
            init_notices_collection()
            print("HW6 Part 1: MongoDB collection ready (s9619_doc.recall_notices).")
            return
        except Exception as exc:  # noqa: BLE001 - any connection error is retried
            last_err = exc
            time.sleep(2)
    print(f"HW6 Part 1 WARNING: could not initialise MongoDB after retries: {last_err}")


def install(app: FastAPI) -> None:
    """Attach the HW6 routes, error handlers and startup hook to an existing app."""
    register_error_handlers(app)
    app.include_router(router)
    app.on_event("startup")(_startup_init_mongo)  # same style as code/main.py


def create_app() -> FastAPI:
    app = FastAPI(title="Grocery Recall Notices - MongoDB document API (HW6)", version="6.0.0")
    # Middleware: CORS for browser clients. JSON request bodies are parsed by
    # FastAPI and validated by the Pydantic models in schemas.py.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    install(app)
    return app


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(create_app(), host="0.0.0.0", port=PORT_BASE)
