"""Part 1.3 Trace lookup page."""
from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

from dashboard import data, loaders


def _chart(rows: list) -> alt.Chart:
    df = pd.DataFrame([{"stage": r["stage"], "start_s": r["start_offset_ms"] / 1000, "end_s": max(r["end_offset_ms"], r["start_offset_ms"] + 20) / 1000,
                        "status": r["status"], "duration_ms": r["duration_ms"]} for r in rows])
    order = list(dict.fromkeys(df["stage"]))
    return alt.Chart(df).mark_bar().encode(
        x=alt.X("start_s:Q", title="seconds since the request began"), x2="end_s:Q",
        y=alt.Y("stage:N", sort=order, title=None),
        color=alt.Color("status:N", scale=alt.Scale(domain=["ok", "error", "timeout"], range=["#2a7f62", "#c0392b", "#d68910"])),
        tooltip=["stage", "duration_ms", "status"]).properties(height=28 * len(order) + 40)


def render() -> None:
    st.title("Trace lookup")
    spans = loaders.spans()
    runs = loaders.examples()
    ex = {"cache_hit": next((r["trace_id"] for r in runs["runs"] if r.get("kind_result") == "hit"), None),
          "cache_miss": next((r["trace_id"] for r in runs["runs"] if r.get("kind_result") == "confirmed_miss"), None),
          "failed": (runs["failed"] or {}).get("trace_id")}
    st.caption("trace_id = the correlation_id that every Kafka message already carries; spans come from reports/hw10/raw/spans.jsonl.")
    st.write("Example traces for the report:")
    cols = st.columns(3)
    for col, (key, label) in zip(cols, (("cache_hit", "Cache hit"), ("cache_miss", "Cache miss (success)"), ("failed", "Failed request"))):
        if col.button(label, disabled=ex[key] is None, width="stretch"):
            st.session_state["trace_input"] = ex[key]
        col.caption(ex[key] or "not captured yet")
    tid = st.text_input("trace_id", key="trace_input", placeholder="paste a trace_id, e.g. f4f5b265-de7c-4ffe-a1f1-8c5353b7b0eb")
    if not tid.strip():
        st.info("Enter a trace_id (or use one of the example buttons) to see the full journey of that request.")
        return
    j = data.journey(spans, tid)
    if not j["found"]:
        st.error(f"No spans found for trace_id {j['trace_id']!r}. Check the id, or that the request ran with tracing on.")
        return
    if j["path"] == "CACHE HIT":
        st.success(f"CACHE HIT path: answered from Redis, the agents did not run. Total {j['total_ms']:.0f} ms.")
    elif j["path"] == "CACHE MISS":
        st.info(f"CACHE MISS path: cache_lookup missed, then the Planner, Writer and Reviewer ran. Total {j['total_ms'] / 1000:.1f} s.")
    else:
        st.info(f"{j['path']}. Total {j['total_ms'] / 1000:.1f} s.")
    if j["request_status"] and j["request_status"] != "ok":
        st.error(f"FAILED request. Failing stage: {j['failing_stage']}. Error: {j['failing_error']}"
                 + (" The message was moved to the dead-letter topic." if j["has_dead_letter"] else ""))
    st.subheader("Request journey in stage order")
    st.dataframe(pd.DataFrame([{k: r[k] for k in ("order", "stage", "scope", "start", "end", "duration_ms", "status", "error", "details")}
                               for r in j["rows"]]), hide_index=True, width="stretch")
    st.altair_chart(_chart(j["rows"]), width="stretch")
    st.caption(f"{len(j['rows'])} spans, {data.ORDER_NOTE} (a span that contains others, such as the whole request, comes first). queue_wait_* = time the message waited on the Kafka topic before the next stage started.")
