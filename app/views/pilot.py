"""Pilot: where each play is in its rollout, and how the pattern scales. Synthetic data."""

import pandas as pd
import streamlit as st

from app import ui
from common.config import load_yaml
from common.paths import ROOT
from engine.catalog import load_catalog

st.title("Pilot")
segments = load_yaml("rollout.yaml")["segments"]
catalog = load_catalog()
st.write(
    f"The pilot runs on one segment: **{', '.join(segments)}** accounts, the ones with no "
    "named success manager. Prove the pattern there, then scale it by changing configuration, "
    "not code."
)

tiers = ui.query(
    "SELECT coverage_tier, count(*) AS accounts, sum(arr) AS arr, avg(health_score) AS avg_health "
    "FROM gold.account_current GROUP BY coverage_tier"
)
tiers["in_pilot"] = tiers["coverage_tier"].isin(segments)
st.dataframe(tiers, hide_index=True, width="stretch")

st.subheader("Rollout stage of each play")
st.caption(
    "slice = 10% of eligible accounts, to check nothing breaks. full = every eligible account, split into treatment and holdout."
)
try:
    results = ui.query(
        "SELECT play_id, n_treatment, n_holdout, verdict, recommendation FROM gold.experiment_results"
    )
except Exception:
    results = pd.DataFrame(
        columns=["play_id", "n_treatment", "n_holdout", "verdict", "recommendation"]
    )
stages = pd.DataFrame(
    [
        {
            "play": play.name,
            "play_id": play.id,
            "stage": play.rollout_stage,
            "holdout": f"{play.holdout_pct:.0%}",
            "ladder": " > ".join(rung.tier for rung in play.intervention_ladder),
            "owner": play.owner,
        }
        for play in catalog.plays
    ]
).merge(results, on="play_id", how="left")
st.dataframe(stages.drop(columns="play_id"), hide_index=True, width="stretch")

st.subheader("Results per rung of the intervention ladder")
st.caption(
    "Digital first, an agent next, a person last. Each play is read on its own success metric. Accounts that reach the human rung are the harder cases."
)
metric_of = {play.id: play.success_metric["id"] for play in catalog.plays}
ladder = ui.query(
    "SELECT play_id, highest_tier, metric, accounts, successes FROM gold.metrics_play_ladder"
)
ladder = ladder[
    [metric_of.get(p) == m for p, m in zip(ladder["play_id"], ladder["metric"], strict=True)]
]
if len(ladder):
    per_tier = ladder.groupby("highest_tier")[["accounts", "successes"]].sum().reset_index()
    per_tier["reached_the_goal"] = [
        ui.pct(s / a) for s, a in zip(per_tier["successes"], per_tier["accounts"], strict=True)
    ]
    st.dataframe(per_tier, hide_index=True, width="stretch")
handoffs = ui.query(
    "SELECT queue, sum(handoffs) AS handoffs, sum(open_now) AS open_now, sum(sla_breaches) AS sla_breaches FROM gold.metrics_handoffs GROUP BY queue"
)
st.write("**What the human rung costs: tasks per queue**")
st.dataframe(handoffs, hide_index=True, width="stretch")

st.subheader("How the pattern scales")
st.markdown(
    """
1. **Slice.** A new play starts on 10% of eligible accounts (`rollout_stage: slice`). The question is "does anything break", not "does it work".
2. **Full test.** Every eligible account in the pilot segment, half held out. The question is "does it move the metric we named before launch".
3. **Next segment.** Add `pooled` to `config/rollout.yaml`. The same plays, rules and guardrails run there; a test in the repository proves it. The holdout comes down to 10% and stays.
4. **Change control.** Each step is a reviewed change to a configuration file, with the experiment report attached (`docs/change-control.md`).
"""
)
plan = ROOT / "docs" / "pilot-plan.md"
if plan.exists():
    with st.expander("The pilot plan"):
        st.markdown(plan.read_text(encoding="utf-8"))
