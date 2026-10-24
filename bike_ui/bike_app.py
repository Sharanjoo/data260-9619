"""HW7 Part 4: Streamlit UI for the Bay Wheels membership agent.

   streamlit run bike_ui\\bike_app.py --server.port 8620

Fields: CSV upload (or one of the two demo scenarios), pricing URL, Run. Panels: live timeline of tool calls and
observations, results (decision, cost comparison, citation), and a metrics strip (steps, time, stop reason, tokens).
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import streamlit as st

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from src.bike_agent import decision_contradicts_totals, stream_agent  # noqa: E402
from src.bike_pricing import evaluate_trips  # noqa: E402
from src.bike_tools import BikeTools  # noqa: E402


def esc(text: str) -> str:
    """Streamlit markdown treats $...$ as math; escape dollar signs so prices display as typed."""
    return text.replace("$", "\\$")

PRICING_URL = "https://www.lyft.com/bikes/bay-wheels/pricing"
DEMOS = {"(upload my own file)": None,
         "Demo scenario M - heavy rider, 540 trips in one month": REPO / "data/bike/scenario_M_membership.csv",
         "Demo scenario P - occasional rider, 504 trips over 72 months": REPO / "data/bike/scenario_P_payperuse.csv"}
SNAP_DIR = REPO / "reports/hw07/raw/bike_snapshots"

st.set_page_config(page_title="Bay Wheels: membership or pay per ride?", layout="wide")
st.title("Bay Wheels: monthly membership or pay per ride?")
st.caption("Sharan Lourduraj - SJSU 018169619 - DATA 260 HW7 Part 4 - local model qwen3:8b, LangChain/LangGraph ReAct agent")

with st.form("inputs"):
    c1, c2 = st.columns([3, 3])
    upload = c1.file_uploader("Trip log CSV (columns: rideable_type, started_at, ended_at, ...)", type=["csv"])
    demo = c1.selectbox("...or use a demo scenario", list(DEMOS))
    url = c2.text_input("Official pricing page URL", PRICING_URL)
    defence = c2.checkbox("Prompt-injection defences on", value=True)
    run = st.form_submit_button("Run", type="primary")

if run:
    if upload is not None:
        tmp = Path(tempfile.mkdtemp()) / "uploaded.csv"
        tmp.write_bytes(upload.getvalue())
        csv_path, source_name = tmp, upload.name
    elif DEMOS[demo] is not None:
        csv_path, source_name = DEMOS[demo], DEMOS[demo].name
    else:
        st.error("Upload a CSV or choose a demo scenario.")
        st.stop()
    try:
        tools = BikeTools(csv_path, [url.strip()], snapshot_dir=SNAP_DIR, label="ui",
                          readonly=True, label_untrusted=defence)
    except Exception as exc:  # noqa: BLE001
        st.error(f"Could not read the CSV: {exc}")
        st.stop()

    left, right = st.columns([1, 1])
    with left:
        st.subheader("Timeline")
        status = st.status(f"Agent running on {source_name} ({tools.row_count} trips)...", expanded=True)
    with right:
        st.subheader("Results")
        results_box = st.container()

    stop = None
    with status:
        for ev in stream_agent(tools, url=url.strip(), prompt_defense=defence):
            if ev["type"] == "tool_call":
                arg_text = ", ".join(f"{k}={str(v)[:90]!r}" for k, v in ev["args"].items())
                st.markdown(esc(f"**Step {ev['step']}** - `{ev['tool']}`({arg_text})  _[{ev['t']} s]_"))
            elif ev["type"] == "observation":
                mark = "ok" if ev["success"] else f"error: {ev['error']}"
                st.caption(esc(f"observation ({mark}): {ev['summary'][:220]}"))
            elif ev["type"] == "final":
                st.markdown("**Final answer ready**")
            elif ev["type"] == "stop":
                stop = ev
        status.update(label=f"Finished: {stop['reason']}", state="complete" if stop["reason"] == "final_answer" else "error", expanded=True)

    parsed = stop["parsed"]
    with results_box:
        if parsed["decision"]:
            st.success(f"Decision: {parsed['decision']}")
        else:
            st.warning("The agent did not give a decision in the required format.")
        if decision_contradicts_totals(parsed):
            st.warning("Check: the agent's decision does not match its own totals (the cheaper option by its numbers is the other one).")
        a, b, c = st.columns(3)
        a.metric("Pay per ride/minute", f"${parsed['pay_per_use_total']:,.2f}" if parsed["pay_per_use_total"] is not None else "n/a")
        b.metric("Monthly membership", f"${parsed['membership_total']:,.2f}" if parsed["membership_total"] is not None else "n/a")
        c.metric("Break-even rides/month (actual)", f"{parsed['break_even']} ({parsed['actual_rides_per_month']})"
                 if parsed["break_even"] is not None else "n/a")
        if parsed["pay_per_use_total"] is not None and parsed["membership_total"] is not None:
            st.bar_chart({"Pay per ride/minute": parsed["pay_per_use_total"], "Monthly membership": parsed["membership_total"]})
        st.text(stop["final_text"] or "(no final answer)")  # plain text: keeps the answer's line breaks and '$' amounts intact
        if stop["snapshots"]:
            s = stop["snapshots"][-1]
            st.caption(esc(f"Citation: pricing page {s['url']} - captured {s['accessed_at']} - SHA-256 {s['sha256']}"))
        with st.expander("Check against the independent calculation"):
            ref = evaluate_trips(csv_path)
            st.write({"reference decision": ref["decision"], "pay-per-use total": ref["pay_per_use_total"],
                      "membership total": ref["membership_total"], "break-even rides/month": ref["break_even_rides_per_month"],
                      "actual rides/month": round(ref["rides_per_month"], 1)})

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Steps (tool calls)", stop["steps"])
    m2.metric("Total time (s)", stop["wall_s"])
    m3.metric("Stop reason", stop["reason"])
    m4.metric("Tokens in / out", f"{stop['input_tokens']} / {stop['output_tokens']}")
