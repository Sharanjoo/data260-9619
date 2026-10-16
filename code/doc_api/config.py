"""HW6 Part 1 - server configuration for the MongoDB document API.

Everything that might change between "running on my laptop", "running inside
Docker Compose" and "running the tests" lives here, so the other modules
(mongo.py, schemas.py, routes.py, server.py) contain no hard-coded settings.
"""
from __future__ import annotations

import os

# --- Section 0 personal configuration (fixed for the semester) -------------
SID4 = 9619
PORT_BASE = 8619
PREFIX = f"s{SID4}"            # -> "s9619"
SEED = SID4
VERIFY_SEED = 260000 + SID4    # -> 269619
DOMAIN_ID = 3

# --- MongoDB connection -----------------------------------------------------
# On the host: mongodb://localhost:27017.  Inside Docker Compose the web
# container gets MONGO_URI=mongodb://mongo:27017 from compose.yaml.
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB_NAME = os.environ.get("MONGO_DB_NAME", f"{PREFIX}_doc")     # "s9619_doc"
NOTICES_COLLECTION = "recall_notices"
SERVER_SELECTION_TIMEOUT_MS = int(os.environ.get("MONGO_TIMEOUT_MS", "3000"))

# --- API ---------------------------------------------------------------------
# /api/notices is already used by the HW2 in-memory routes, so the HW6
# document API lives under its own prefix.
API_PREFIX = "/api/hw6/notices"

# --- Field limits shared by Pydantic and the MongoDB $jsonSchema validator -----
TITLE_MAX_LENGTH = 100
DESCRIPTION_MAX_LENGTH = 1000
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200

# --- CORS (used by the standalone app in server.py; main.py already has its own)
CORS_ORIGINS = [
    "http://localhost:5174",   # Vite React client
    "http://localhost:8619",   # same-origin pages served by the API itself
]
