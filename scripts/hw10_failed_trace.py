"""HW10 Part 4.2: capture ONE failed request and show where it failed.

How the failure is produced (nothing in the code is changed): the normal Writer is stopped and a Writer that points at a model
which does not exist is started in the same consumer group. The Planner works, the broken Writer fails every attempt (Ollama
answers 404), the message goes to s9619_dead_letter after 3 attempts, and the client gives up at the timeout.

    1. stop the normal Writer (Ctrl+C in its terminal); keep the Planner and the Reviewer running
    2. in a new terminal:   $env:OLLAMA_MODEL="no-such-model"; python code/kafka_agents/writer.py --instance B
    3. in this terminal:    python scripts/hw10_failed_trace.py
    4. afterwards: Ctrl+C the broken Writer and start the normal one again

Writes data/hw10/failed_trace.json (trace_id, question, every span of that trace, failing stage and error)."""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("HW9_AGENT_TIMEOUT", "180")  # seconds the client waits for a final message before it gives up

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "code"))

from tracing.spans import DEFAULT_PATH, read_spans  # noqa: E402

QUESTION = "A tray of Sliced Turkey Breast I bought last week was recalled for possible Listeria. Can I still use the slices I have left?"
OUT = REPO / "data" / "hw10" / "failed_trace.json"
BANNER = "Sharan Lourduraj | SID4 9619 | DATA 260 HW10 Part 4.2 (failed trace)"


async def main() -> int:
    import redis
    from cache_layer.agent_client import AgentClient
    from cache_layer.config import REDIS_HOST, REDIS_PORT
    from cache_layer.embedder import Embedder
    from cache_layer.facts import FactsStore
    from cache_layer.ingress import SemanticIngress
    from cache_layer.semantic_cache import SemanticCache

    print(BANNER, flush=True)
    cache = SemanticCache(redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True))
    cache.ensure_index()
    embedder = Embedder()
    embedder.encode("warm up")
    agent = AgentClient()
    await agent.start()
    try:
        res = await SemanticIngress(cache, embedder, FactsStore(), agent, threshold=0.95).answer(QUESTION, tag="failed-trace")
    finally:
        await agent.stop()
    tid = res["trace_id"]
    print(f"\nrequest finished: status={res['status']} is_cached={res['is_cached']} latency={res['latency_ms'] / 1000:.0f}s trace_id={tid}")
    spans = sorted((s for s in read_spans(DEFAULT_PATH) if s["trace_id"] == tid), key=lambda s: s["start_ms"])
    for s in spans:
        print(f"  {s['stage']:20s} {s['duration_ms']:>10.1f} ms  {s['status']:7s} {s['error'] or ''}")
    errors = [s for s in spans if s["status"] != "ok"]
    failing = next((s for s in errors if s["stage"] in ("planner", "writer", "reviewer")), None)
    dl = next((s for s in spans if s["stage"] == "dead_letter"), None)
    summary = {"trace_id": tid, "question": QUESTION, "request_status": res["status"],
               "failing_stage": failing["stage"] if failing else None, "error": failing["error"] if failing else None,
               "dead_lettered": dl is not None, "spans": spans}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nfailing stage: {summary['failing_stage']}   error: {summary['error']}   dead-lettered: {summary['dead_lettered']}")
    print(f"wrote {OUT.relative_to(REPO)}")
    return 0 if failing else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
