"""HW9 settings. Every Redis key starts with PREFIX. Scripts on the laptop reach Redis on 127.0.0.1:46379 and MySQL on
127.0.0.1:43306 (the host-side ports from compose.yaml); inside Docker the same services are redis:6379 / mysql:3306."""
from __future__ import annotations

import os

SID4 = "9619"
PREFIX = "s9619"
SEED = 9619
VERIFY_SEED = 269619
PORT_BASE = 8619
BANNER = "Sharan Lourduraj | SID4 9619 | DATA 260 HW9"

REDIS_HOST = os.environ.get("REDIS_HOST", "127.0.0.1")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "46379"))

# code/db.py reads these when it is imported, so the laptop defaults are set before that import happens.
os.environ.setdefault("MYSQL_HOST", "127.0.0.1")
os.environ.setdefault("MYSQL_PORT", "43306")

VIEWS_SYNC_EVERY = 10

# --- Parts 2-3: semantic response cache ---
CACHE_INDEX = f"{PREFIX}_cache_idx"       # RediSearch index name
CACHE_KEY_PREFIX = f"{PREFIX}:cache:"     # every cached entry (hash) lives under this prefix
EMBED_MODEL = os.environ.get("HW9_EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
EMBED_DIM = 384
DEFAULT_THRESHOLD = 0.85
NO_DEPENDENCY = "none"                    # depends_on / data_version value for answers that read no database record
AGENT_TIMEOUT_S = float(os.environ.get("HW9_AGENT_TIMEOUT", "600"))
