"""Part 1.2 Evaluation page."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard import data, loaders


def _fmt(x, digits=2):
    return "n/a" if x is None else f"{x:.{digits}f}"


def render() -> None:
    st.title("Evaluation")
    results = data.latest_evaluations(loaders.evals())
    st.header("Part 2: pipeline evaluation (local judge, 1-5 scale)")
    st.caption("Source: reports/hw10/raw/evaluations.jsonl, newest result per trace_id. Judge: GEval on a local Ollama model; "
               "1 = very poor, 5 = excellent. Final minus draft is the Reviewer's effect.")
    if not results:
        st.info("No evaluation results yet.")
    else:
        st.subheader("Scores by pipeline stage")
        stage = data.stage_scores(results)
        st.dataframe(pd.DataFrame([{**r, "mean_score": None if r["mean_score"] is None else round(r["mean_score"], 2)} for r in stage]),
                     hide_index=True, width="stretch")
        st.bar_chart(pd.DataFrame({"mean score": [r["mean_score"] or 0 for r in stage]}, index=[r["stage"] for r in stage]))
        st.subheader("Scores by case")
        st.dataframe(pd.DataFrame(data.case_table(results)), hide_index=True, width="stretch")
        st.subheader("What the scores suggest about Planner, Writer and Reviewer")
        for line in data.interpretation(results):
            st.write("- " + line)
        with st.expander("Judge reasons and the final answer for one case"):
            pick = st.selectbox("trace_id", [r["trace_id"] for r in results])
            r = next(x for x in results if x["trace_id"] == pick)
            for key, label in (("plan_quality", "Plan quality"), ("writer_helpfulness", "Writer helpfulness"),
                               ("final_helpfulness", "Final answer helpfulness")):
                sc = r["scores"][key]
                st.write(f"**{label}: {sc['score']}**  {sc['reason'] or sc['error'] or ''}")
            st.write("Final answer:", r["inputs"]["final_answer"])
            st.write("Interpretation:", r["improvement"]["interpretation"])

    st.header("Part 3: how far can the judge be trusted?")
    v = loaders.validation()
    if not v or "agreement_run1" not in v:
        st.info("Judge validation has not been run yet (needs the 20 hand labels and scripts/hw10_judge_validate.py).")
        return
    a = v["agreement_run1"]
    st.caption("Source: reports/hw10/raw/judge_validation.json and judge_validation_per_case.csv. Human labels are the reference; "
               "agreement uses judge run 1 on the same 20 Writer drafts.")
    c = st.columns(4)
    c[0].metric("Spearman correlation", _fmt(a["spearman"]))
    c[1].metric("Mean absolute difference", _fmt(a["mean_abs_diff"]))
    c[2].metric("Bias (judge - human)", f"{a['mean_signed_diff_judge_minus_human']:+.2f}")
    c[3].metric("Within 1 point", f"{a['within_1']:.0%}")
    rep = v.get("repeatability")
    if rep:
        st.subheader(f"Repeatability over {len(rep['runs'])} runs of the same drafts")
        r = st.columns(3)
        r[0].metric("Cases whose score changed", f"{rep['cases_changed']} of {rep['n_cases']}", f"{rep['fraction_changed']:.0%}", delta_color="off")
        r[1].metric("Mean absolute change", _fmt(rep["mean_abs_change_between_runs"]))
        r[2].metric("Max absolute change", rep["max_abs_change_between_runs"])
    rows = loaders.per_case()
    if rows:
        st.subheader("Raw per-case data (human label vs judge runs)")
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
