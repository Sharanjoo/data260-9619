"""HW6 Part 2 - memory settings. Every value can be overridden by an environment variable
so Part 3 can sweep SHORT_TERM_N without touching code."""
from __future__ import annotations

import os

SID4 = 9619
SEED = 9619

# --- collections (same database as Part 1: s9619_doc) -------------------------------
MESSAGES_COLLECTION = "messages"
SUMMARIES_COLLECTION = "summaries"
EPISODES_COLLECTION = "episodes"

# --- memory behaviour -----------------------------------------------------------------
SHORT_TERM_N = int(os.environ.get("SHORT_TERM_N", "12"))                       # sliding window size
SUMMARIZE_EVERY_USER_MSGS = int(os.environ.get("SUMMARIZE_EVERY_USER_MSGS", "5"))  # "M"
LIFETIME_EVERY_SESSION_SUMMARIES = int(os.environ.get("LIFETIME_EVERY_SESSION_SUMMARIES", "2"))
EPISODE_TOP_K = int(os.environ.get("EPISODE_TOP_K", "3"))
EPISODE_MIN_SIMILARITY = float(os.environ.get("EPISODE_MIN_SIMILARITY", "0.45"))
EPISODE_DUPLICATE_SIMILARITY = 0.95   # a new fact this close to a stored one is not stored again
MAX_FACTS_PER_MESSAGE = 3
MAX_FACT_CHARS = 200
EPISODE_SCAN_LIMIT = 500              # newest episodes compared by cosine similarity per turn
# Window policy used by Part 3: "none" (plain sliding window) or "compress_old_assistant".
COMPRESSION_POLICY = os.environ.get("COMPRESSION_POLICY", "none")

# --- GET /api/memory sizes ------------------------------------------------------------
MEMORY_VIEW_MESSAGES = 16
MEMORY_VIEW_EPISODES = 20
AGGREGATE_RECENT_SUMMARIES = 5

# --- models (local Ollama only) -------------------------------------------------------
# Inside Docker, Ollama on the Windows host is reached as host.docker.internal.
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
CHAT_MODEL = os.environ.get("CHAT_MODEL", "qwen3:8b")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "nomic-embed-text")
OLLAMA_TIMEOUT_SECONDS = float(os.environ.get("OLLAMA_TIMEOUT_SECONDS", "300"))
CHAT_TEMPERATURE = 0.0   # deterministic replies keep the Part 3 sweep comparable
NUM_CTX = int(os.environ.get("NUM_CTX", "8192"))

# --- input limits -----------------------------------------------------------------------
MAX_MESSAGE_CHARS = 4000
ID_PATTERN = r"^[A-Za-z0-9_.:-]{1,64}$"

SYSTEM_PRIMER = (
    "You are the assistant inside a grocery recall notice app. Answer helpfully and briefly "
    "(at most three sentences). You may be given a long-term summary, a session summary and "
    "remembered facts about this user; use them when relevant, and if you do not know "
    "something about the user, say so instead of guessing."
)
