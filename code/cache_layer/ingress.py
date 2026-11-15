"""HW9 Parts 2-3: the semantic cache at the ingress of the Q&A endpoint, in front of the HW8 agent pipeline.

    query -> embed -> nearest cached query in Redis (cosine) -> similarity >= threshold ?
        yes: return the stored final answer, is_cached = true, no agent runs
        no : run Planner -> Writer -> Reviewer through Kafka, store query + embedding + answer + data version,
             return the answer with is_cached = false

Every call returns the flag, the similarity, the latency and the stage timings, and (when a metrics file is given)
appends the same record as one JSON line."""
from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from kafka_api.logutil import log

from cache_layer.config import DEFAULT_THRESHOLD, NO_DEPENDENCY
from cache_layer.facts import facts_text, find_record_code, fingerprint
from tracing.spans import emit as trace_emit, now_ms


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _ms(t0: float) -> float:
    return round((time.perf_counter() - t0) * 1000, 2)


class SemanticIngress:
    def __init__(self, cache: Any, embedder: Any, facts: Any, agent: Any, threshold: float = DEFAULT_THRESHOLD,
                 metrics_path: Optional[Path] = None) -> None:
        self.cache, self.embedder, self.facts, self.agent = cache, embedder, facts, agent
        self.threshold = threshold
        self.metrics_path = Path(metrics_path) if metrics_path else None

    async def answer(self, query: str, threshold: Optional[float] = None, use_cache: bool = True,
                     check_version: bool = False, tag: Optional[str] = None) -> Dict[str, Any]:
        thr = self.threshold if threshold is None else threshold
        t_start, started = time.perf_counter(), _now()
        timings: Dict[str, float] = {}
        cid = str(uuid.uuid4())  # HW10: the trace_id. It is the HW8 correlation_id, created first so hits and misses both have one
        start_ms = now_ms()
        result: Dict[str, Any] = {"query": query, "threshold": thr, "started_at": started, "tag": tag,
                                  "correlation_id": cid, "trace_id": cid, "_start_ms": start_ms,
                                  "is_cached": False, "similarity": None, "matched_query": None,
                                  "stale_entry_removed": False}
        vec = None
        if use_cache:
            t = time.perf_counter()
            vec = self.embedder.encode_bytes(query)
            timings["embed_ms"] = _ms(t)
            t = time.perf_counter()
            entry, sim = self.cache.lookup(vec)
            timings["search_ms"] = _ms(t)
            result["similarity"] = sim
            result["matched_query"] = entry["query"] if entry else None
            lookup_end = now_ms()
            trace_emit(cid, "cache_lookup", start_ms, lookup_end, hit=bool(entry is not None and sim >= thr),
                       similarity=sim, threshold=thr, embed_ms=timings["embed_ms"], search_ms=timings["search_ms"])
            if entry is not None and sim >= thr:
                stale = False
                if check_version and entry["depends_on"] != NO_DEPENDENCY:
                    t = time.perf_counter()
                    current = self.facts.version(entry["depends_on"])
                    timings["version_check_ms"] = _ms(t)
                    if current != entry["data_version"]:
                        stale = True
                        self.cache.delete(entry["key"])
                        result["stale_entry_removed"] = True
                        log("CACHE", f"STALE entry removed: {entry['depends_on']} changed since it was cached "
                                     f"(stored version {entry['data_version']}, now {current}); similarity={sim:.4f}")
                if not stale:
                    result.update(is_cached=True, answer=entry["answer"], status="cached",
                                  cached_data_version=entry["data_version"], depends_on=entry["depends_on"])
                    log("CACHE", f"HIT similarity={sim:.4f} threshold={thr} matched={entry['query']!r}")
                    return self._finish(result, timings, t_start)
            log("CACHE", f"MISS similarity={sim:.4f} threshold={thr}"
                         + (f" nearest={entry['query']!r}" if entry else " (cache empty)"))

        code = find_record_code(query)
        facts = self.facts.load(code) if code else None
        question = f"{query}\n\n{facts_text(facts)}" if facts else query
        version = fingerprint(facts) if facts else NO_DEPENDENCY
        depends_on = code if facts else NO_DEPENDENCY
        t = time.perf_counter()
        log("CACHE", f"running the agent pipeline correlation_id={cid} depends_on={depends_on}")
        agent_start = now_ms()
        final = await self.agent.run(question, cid, entity_key=code)
        timings["agent_ms"] = _ms(t)
        trace_emit(cid, "agent_pipeline", agent_start, now_ms(), "timeout" if final is None else "ok",
                   "no final message before the agent timeout" if final is None else None,
                   final_status=(final or {}).get("status"))
        result.update(depends_on=depends_on, data_version=version)
        if final is None:
            result.update(answer=None, status="timeout")
            log("CACHE", f"agent pipeline gave no answer for correlation_id={cid}")
            return self._finish(result, timings, t_start)
        result.update(answer=final.get("answer"), status=final.get("status"))
        if use_cache and final.get("status") == "approved" and final.get("answer"):
            t = time.perf_counter()
            self.cache.store(query, vec, final["answer"], data_version=version, depends_on=depends_on)
            timings["store_ms"] = _ms(t)
            log("CACHE", f"stored answer for {query!r} depends_on={depends_on} data_version={version}")
        elif use_cache:
            log("CACHE", f"answer not stored: status={final.get('status')}")
        return self._finish(result, timings, t_start)

    def _finish(self, result: Dict[str, Any], timings: Dict[str, float], t_start: float) -> Dict[str, Any]:
        result["timings"] = timings
        result["latency_ms"] = _ms(t_start)
        result["finished_at"] = _now()
        start_ms = result.pop("_start_ms")
        ok = result.get("status") in ("cached", "approved")
        trace_emit(result["trace_id"], "request", start_ms, now_ms(), "ok" if ok else "error",
                   None if ok else f"request ended with status={result.get('status')}",
                   is_cached=result.get("is_cached"), answer_status=result.get("status"), tag=result.get("tag"),
                   similarity=result.get("similarity"), latency_ms=result["latency_ms"])
        if self.metrics_path:
            self.metrics_path.parent.mkdir(parents=True, exist_ok=True)
            with self.metrics_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(result, ensure_ascii=False) + "\n")
        return result
