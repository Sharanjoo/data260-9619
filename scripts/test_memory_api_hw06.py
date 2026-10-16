"""Run: python scripts/test_memory_api_hw06.py  (needs: pip install mongomock)
Offline tests for the HW6 Part 2 memory API (mongomock + fake model/embedder; no Ollama needed)."""
import hashlib
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "code"))

import mongomock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from memory_api import config, routes
from memory_api.episodes import EXTRACTION_PROMPT
from memory_api.prompt import apply_window_policy, split_prompt_tokens
from memory_api.summaries import LIFETIME_SUMMARY_PROMPT, SESSION_SUMMARY_PROMPT
from memory_api.server import install
from memory_api.store import get_database


class FakeChat:
    """Deterministic stand-in for the Ollama adapter."""
    def __init__(self):
        self.calls = []
    def complete(self, messages, *, json_schema=None):
        self.calls.append(messages)
        system = messages[0]["content"]
        user = messages[-1]["content"]
        if system == EXTRACTION_PROMPT:
            facts = []
            m = re.search(r"allergic to ([a-z]+)", user.lower())
            if m:
                facts.append({"fact": f"User is allergic to {m.group(1)}", "importance": 1.4})
            m = re.search(r"i live in ([a-z ]+)", user.lower())
            if m:
                facts.append({"fact": f"User lives in {m.group(1).strip()}", "importance": 0.6})
            content = json.dumps({"facts": facts})
        elif system == SESSION_SUMMARY_PROMPT:
            content = "- session bullet"
        elif system == LIFETIME_SUMMARY_PROMPT:
            content = "- lifetime bullet"
        else:
            content = "Sure. Here is a reply. More text follows."
        words = sum(len(m["content"].split()) for m in messages)
        return SimpleNamespace(content=content, input_tokens=words * 2, output_tokens=7, total_tokens=0,
                               model="fake", total_duration_ns=5_000_000, raw={})


class FakeEmbedder:
    def embed(self, text):
        vec = [0.0] * 64
        for w in re.findall(r"[a-z]+", text.lower()):
            vec[int(hashlib.md5(w.encode()).hexdigest(), 16) % 64] += 1.0
        return vec


db = mongomock.MongoClient(tz_aware=True)["s9619_doc"]
chat_model, embedder = FakeChat(), FakeEmbedder()
app = FastAPI()
install(app)
app.dependency_overrides[get_database] = lambda: db
app.dependency_overrides[routes.get_chat_model] = lambda: chat_model
app.dependency_overrides[routes.get_embedder] = lambda: embedder
c = TestClient(app, raise_server_exceptions=False)
passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    passed += bool(cond); failed += (not cond)
    print(("PASS" if cond else "FAIL"), name, detail)


def chat(msg, sid=None, uid="u1", **extra):
    body = {"user_id": uid, "message": msg, **extra}
    if sid:
        body["session_id"] = sid
    return c.post("/api/chat", json=body)


# --- first turn creates a session ---
r = chat("Hi, I am allergic to peanuts and I live in San Jose")
j = r.json()
check("chat 200", r.status_code == 200, r.text[:120])
sid = j["session_id"]
check("session id generated", sid.startswith("sess-"))
check("reply returned", j["reply"].startswith("Sure"))
check("two episodes stored (importance clipped to <=1)", len(j["memory_events"]["episodes_stored"]) == 2 and j["memory_events"]["episodes_stored"][0]["importance"] == 1.0, str(j["memory_events"]))
check("window has only current msg", j["memory_used"]["short_term"]["count"] == 1)
check("no summaries yet", j["memory_used"]["long_term"] == {"lifetime_summary": None, "session_summary": None})
check("components sum to prompt tokens", sum(j["metrics"]["tokens_by_component"].values()) == j["metrics"]["prompt_tokens"], str(j["metrics"]["tokens_by_component"]))
check("overhead tokens logged", j["metrics"]["memory_overhead_prompt_tokens"] > 0)
check("collections populated", db.messages.count_documents({}) == 2 and db.episodes.count_documents({}) == 2)

# --- later turns: window grows, retrieval finds the allergy ---
for i in range(2, 5):
    chat(f"message number {i} about cheese", sid)
r = chat("what am i allergic to peanuts", sid)
j = r.json()
check("window count 9 (5 user + 4 replies before)", j["memory_used"]["short_term"]["count"] == 9, str(j["memory_used"]["short_term"]["count"]))
check("episodic retrieval returns the allergy fact", any("peanuts" in e["fact"] for e in j["memory_used"]["episodic"]), str(j["memory_used"]["episodic"]))
check("5th user msg triggers session summary", j["memory_events"]["session_summary_updated"] is True)
check("lifetime not yet (needs 2 session summaries)", j["memory_events"]["lifetime_summary_updated"] is False)
last_prompt = chat_model.calls[-3]  # chat call of the 5th turn is before extraction+summary calls
sys_text = last_prompt[0]["content"]
check("episodic facts are in the FINAL user message", "Remembered facts about this user" in last_prompt[-1]["content"] and "peanuts" in last_prompt[-1]["content"])

# --- window limit and override ---
r = chat("another message", sid, short_term_n=4)
check("short_term_n override respected", r.json()["memory_used"]["short_term"]["count"] == 4 and r.json()["metrics"]["short_term_n"] == 4)
check("session summary now in prompt", r.json()["memory_used"]["long_term"]["session_summary"] == "- session bullet")

# --- lifetime summary after 3 session summaries (messages 5, 10, 15) ---
for i in range(7, 16):
    j = chat(f"filler {i}", sid).json()
check("15th user msg: lifetime summary created", db.summaries.count_documents({"scope": "user"}) == 1)
life = db.summaries.find_one({"scope": "user"})
check("lifetime doc has session_id null", life["session_id"] is None)
check("3 session summaries stored", db.summaries.count_documents({"scope": "session"}) == 3)

# --- new session for same user sees lifetime summary + cross-session episodes ---
r = chat("allergic to peanuts again", None)
j = r.json()
check("new session id differs", j["session_id"] != sid)
check("lifetime summary visible in new session", j["memory_used"]["long_term"]["lifetime_summary"] == "- lifetime bullet")
check("cross-session episodic recall", any("peanuts" in e["fact"] for e in j["memory_used"]["episodic"]))

# --- duplicate facts are not stored twice ---
before = db.episodes.count_documents({})
chat("I am allergic to peanuts", j["session_id"])
check("duplicate fact skipped", db.episodes.count_documents({}) == before)

# --- GET /api/memory ---
m = c.get("/api/memory/u1").json()
check("memory: <=16 messages", 0 < len(m["messages"]) <= 16, str(len(m["messages"])))
check("memory: chronological", [x["created_at"] for x in m["messages"]] == sorted(x["created_at"] for x in m["messages"]))
check("memory: summaries present", m["session_summary"] is not None and m["lifetime_summary"]["scope"] == "user")
check("memory: episodes without raw vectors", m["episodes"] and "embedding" not in m["episodes"][0] and m["episodes"][0]["embedding_dim"] == 64)
check("memory: unknown user is empty", c.get("/api/memory/nobody").json()["messages"] == [])
check("memory: bad user id 422", c.get("/api/memory/bad%20id!").status_code == 422)

# --- GET /api/aggregate ---
a = c.get("/api/aggregate/u1").json()
check("aggregate: one day", len(a["daily_message_counts"]) == 1, str(a["daily_message_counts"]))
day = a["daily_message_counts"][0]
check("aggregate: counts add up", day["messages"] == day["user_messages"] + day["assistant_messages"] == a["total_messages"] == db.messages.count_documents({"user_id": "u1"}))
check("aggregate: sessions=2, summaries<=5", a["sessions"] == 2 and 0 < len(a["recent_summaries"]) <= 5)

# --- validation ---
check("empty message 422", c.post("/api/chat", json={"user_id": "u1", "message": ""}).status_code == 422)
check("missing user 422", c.post("/api/chat", json={"message": "hi"}).status_code == 422)
check("bad user id 422", c.post("/api/chat", json={"user_id": "a b", "message": "hi"}).status_code == 422)
check("unknown field 422", c.post("/api/chat", json={"user_id": "u1", "message": "hi", "x": 1}).status_code == 422)

# --- model down -> 502, user message kept ---
from memory_api.llm import ModelClientError
class Down:
    def complete(self, *a, **k): raise ModelClientError("Cannot reach Ollama")
app.dependency_overrides[routes.get_chat_model] = lambda: Down()
r = chat("hello?", "sess-down")
check("model down -> 502 model_unavailable", r.status_code == 502 and r.json()["error"] == "model_unavailable", r.text[:100])
app.dependency_overrides[routes.get_chat_model] = lambda: chat_model

# --- read-only probe mode writes nothing ---
before = (db.messages.count_documents({}), db.episodes.count_documents({}), db.summaries.count_documents({}))
r = chat("I am allergic to walnuts; what allergy do I have", sid, read_only=True)
after = (db.messages.count_documents({}), db.episodes.count_documents({}), db.summaries.count_documents({}))
check("read_only: nothing written", before == after and r.status_code == 200, f"{before} {after}")
check("read_only: window ends with current message", r.json()["memory_used"]["short_term"]["messages"][-1]["content"].startswith("I am allergic to walnuts"))
check("read_only: flagged in metrics, no overhead", r.json()["metrics"]["read_only"] is True and r.json()["metrics"]["memory_overhead_prompt_tokens"] == 0)
# newer fact ordering: facts reach the prompt oldest-first
from memory_api.prompt import episodic_text
txt = episodic_text([{"fact": "B new", "created_at": "2026-10-02T00:00:00Z"}, {"fact": "A old", "created_at": "2026-10-01T00:00:00Z"}])
check("episodic facts ordered oldest first", txt.index("A old") < txt.index("B new") and "newer fact replaces" in txt)

# --- config / fingerprint endpoint ---
cfg = c.get("/api/memory-config").json()
check("memory-config reports settings + fingerprint", cfg["short_term_n_default"] == config.SHORT_TERM_N and len(cfg["source_fingerprint"]) == 16, str(cfg))

# --- compression policy ---
hist = [{"role": "user", "content": "u1"}, {"role": "assistant", "content": "First sentence here. Second long sentence."},
        {"role": "user", "content": "u2"}, {"role": "assistant", "content": "Keep this. Whole."}]
out = apply_window_policy(hist, "compress_old_assistant")
check("policy shrinks old assistant reply", out[1]["content"] == "First sentence here." and out[3]["content"] == "Keep this. Whole.")
check("policy none leaves window alone", apply_window_policy(hist, "none") == hist)
check("split_prompt_tokens exact sum", sum(split_prompt_tokens({"a": "x" * 40, "b": "y" * 7, "c": ""}, 101).values()) == 101)

print(f"\n{passed}/{passed + failed} checks passed")
sys.exit(1 if failed else 0)
