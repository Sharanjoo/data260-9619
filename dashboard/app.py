"""HW10 Part 1: operations dashboard for the Planner -> Writer -> Reviewer pipeline behind the semantic cache.

    streamlit run dashboard/app.py --server.port 8620

Pages: Summary (requests, cache hit rate, errors, latency), Evaluation (Part 2 scores and Part 3 judge validation),
Trace lookup (one request's journey by trace_id). Reads only the saved logs under reports/hw10/raw and data/hw10."""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dashboard import data, view_evaluation, view_summary, view_trace  # noqa: E402

st.set_page_config(page_title="HW10 pipeline operations", layout="wide")


@st.cache_resource
def config() -> dict:
    """Created once per server process and shared by every page and session: where the logs are."""
    return {"banner": data.BANNER, "spans": data.SPANS, "evals": data.EVALS, "validation": data.VALIDATION}


st.sidebar.markdown(f"**{config()['banner']}**")
st.sidebar.caption("Grocery recall notices: Planner, Writer, Reviewer behind a Redis semantic cache")
if st.sidebar.button("Reload logs"):
    st.cache_data.clear()

page = st.navigation([
    st.Page(view_summary.render, title="Summary", url_path="summary", default=True),
    st.Page(view_evaluation.render, title="Evaluation", url_path="evaluation"),
    st.Page(view_trace.render, title="Trace lookup", url_path="trace"),
])
page.run()
