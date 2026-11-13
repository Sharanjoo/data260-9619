"""Part 1.1 Summary page."""
from __future__ import annotations

import time
from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from dashboard import data, loaders
from tracing.stats import per_request, summarize


def _ts(ms) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC") if ms else "-"


def _sec(ms) -> str:
    return "-" if ms is None else (f"{ms:.0f} ms" if ms < 1000 else f"{ms / 1000:.1f} s")


def render() -> None:
    st.title("Summary")
    spans = loaders.spans()
    choice = st.radio("Time window", list(data.WINDOWS), index=3, horizontal=True)
    all_rows = data.requests_from_spans(spans)
    rows = data.in_window(all_rows, time.time() * 1000, data.WINDOWS[choice])
    s = data.summarize_requests(rows)
    src = "reports/hw10/raw/spans.jsonl (one 'request' span per call to the cache ingress; the span has is_cached, status, duration)"
    window = (f"Window: {choice} -> {_ts(s['first_request_ms'])} to {_ts(s['last_request_ms'])} ({s['requests']} requests). "
              f"Source: {src}.")
    if not rows:
        st.warning(f"No requests in this window. {window}")
        return
    if s["cache_enabled"] == 0:
        st.warning(f"No request in this window went through the cache. {window}")

    st.subheader("Recent requests")
    st.metric("Requests", s["requests"], f"{s['cache_enabled']} through the cache, {s['cache_bypassed']} with the cache bypassed", delta_color="off")
    st.caption(window)

    st.subheader("Semantic cache: hits and misses are separate")
    c1, c2, c3 = st.columns(3)
    c1.metric("Cache hit rate", "n/a" if s["hit_rate"] is None else f"{s['hit_rate']:.0%}", f"{s['hits']} hits")
    c2.metric("Cache miss rate", "n/a" if s["miss_rate"] is None else f"{s['miss_rate']:.0%}", f"{s['misses']} misses (agents ran)")
    c3.metric("Cache hit latency p50", _sec(s["latency_hit"]["p50_ms"]))
    st.caption(f"{window} A hit = the cache_lookup span says hit=true (similarity >= the threshold); everything else is a miss and ran the "
               "Planner, Writer and Reviewer. Rates use only requests that went through the cache; requests that bypassed it (the Part 3 drafts, "
               "cache switched off) are counted above but excluded here.")
    st.dataframe(pd.DataFrame([
        {"path": "Cache hit", "requests": s["hits"], "share": "n/a" if s["hit_rate"] is None else f"{s['hit_rate']:.0%}", "p50": _sec(s["latency_hit"]["p50_ms"]),
         "p95": _sec(s["latency_hit"]["p95_ms"]), "mean": _sec(s["latency_hit"]["mean_ms"])},
        {"path": "Cache miss", "requests": s["misses"], "share": "n/a" if s["miss_rate"] is None else f"{s['miss_rate']:.0%}", "p50": _sec(s["latency_miss"]["p50_ms"]),
         "p95": _sec(s["latency_miss"]["p95_ms"]), "mean": _sec(s["latency_miss"]["mean_ms"])}]), hide_index=True, width="stretch")

    st.subheader("Error rate and end-to-end latency")
    e1, e2, e3 = st.columns(3)
    e1.metric("Error rate", f"{s['error_rate']:.1%}", f"{s['errors']} of {s['requests']} requests ended in error", delta_color="off")
    e2.metric("End-to-end latency p50 (all)", _sec(s["latency_all"]["p50_ms"]))
    e3.metric("End-to-end latency p95 (all)", _sec(s["latency_all"]["p95_ms"]))
    stage_errors = data.stage_error_spans(spans, rows)
    st.caption(f"{window} Error = the request span has status 'error' (the request ended without an approved answer, e.g. the agents "
               f"timed out). Stage-level error spans, including attempts that were retried: {len(stage_errors)}. "
               "The all-requests latency mixes ~100 s misses with sub-second hits, so read the hit and miss rows above too.")
    if s["error_trace_ids"]:
        st.write("Failed traces (paste one into Trace lookup):", ", ".join(s["error_trace_ids"][:5]))

    st.subheader("Where a cache miss spends its time")
    by_trace: dict = {}
    for sp in spans:
        by_trace.setdefault(sp["trace_id"], []).append(sp)
    miss_rows = [per_request(r["trace_id"], by_trace[r["trace_id"]]) for r in rows if r["cache_enabled"] and not r["is_cached"] and r["status"] == "ok"]
    miss_rows = [m for m in miss_rows if m]
    if miss_rows:
        tab = [t for t in summarize(miss_rows) if not t["stage"].startswith("Evaluation")]
        st.dataframe(pd.DataFrame([{"stage": t["stage"], "p50 (ms)": round(t["p50_ms"]), "p95 (ms)": round(t["p95_ms"]),
                                    "% of end-to-end (mean)": round(t["share_mean_pct"], 1)} for t in tab]),
                     hide_index=True, width="stretch")
        st.caption(f"{window} Only successful misses that have the full set of spans ({len(miss_rows)} requests). "
                   "Cache-hit latency is shown separately above and is not part of this table.")
    else:
        st.info("No complete cache-miss traces in this window yet.")
