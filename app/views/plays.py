"""Plays and experiments: what runs, for whom, and whether it works. Synthetic data."""

import altair as alt
import pandas as pd
import streamlit as st

from app import ui
from engine.catalog import load_catalog

st.title("Plays and experiments")
catalog = load_catalog()

st.subheader("The play catalog")
st.caption(
    "Plays are configuration (`config/plays.yaml`). Consent, frequency caps and holdouts are enforced by the engine for all of them."
)
st.dataframe(
    pd.DataFrame(
        [
            {
                "priority": play.priority,
                "play": play.name,
                "trigger": ", ".join(play.trigger),
                "ladder": " > ".join(rung.tier for rung in play.intervention_ladder),
                "stage": play.rollout_stage,
                "holdout": f"{play.holdout_pct:.0%}",
                "success metric": play.success_metric["id"],
                "owner": play.owner,
            }
            for play in catalog.plays
        ]
    ),
    hide_index=True,
    width="stretch",
)

st.subheader("Results against the holdout")
try:
    results = ui.query("SELECT * FROM gold.experiment_results")
except Exception:
    results = pd.DataFrame()
if results.empty:
    st.info("No results yet. Run `uv run python run.py experiments`.")
    st.stop()

st.caption(
    f"As of {results['as_of'][0]}. This is a simulation: any lift comes from the assumptions in "
    "`config/sim_effects.yaml`. What is real is the measurement."
)
table = results.assign(
    treatment=[
        f"{ui.pct(r)} ({s}/{n})" if n else "none"
        for r, s, n in zip(
            results["rate_treatment"],
            results["successes_treatment"],
            results["n_treatment"],
            strict=True,
        )
    ],
    holdout=[
        f"{ui.pct(r)} ({s}/{n})" if n else "none"
        for r, s, n in zip(
            results["rate_holdout"], results["successes_holdout"], results["n_holdout"], strict=True
        )
    ],
    lift=[f"{value:+.0%}" if pd.notna(value) else "n/a" for value in results["lift"]],
    p=[f"{value:.3f}" if pd.notna(value) else "n/a" for value in results["p_value"]],
)
st.dataframe(
    table[
        ["play_name", "metric", "treatment", "holdout", "lift", "p", "verdict", "recommendation"]
    ],
    hide_index=True,
    width="stretch",
)

measured = results.dropna(subset=["lift"])
if len(measured):
    st.write(
        "**Lift on the success metric, with its 95% interval.** An interval that crosses zero means the play may have done nothing."
    )
    base = alt.Chart(measured).encode(y=alt.Y("play_name:N", title=None, sort=None))
    bars = base.mark_errorbar().encode(
        x=alt.X(
            "ci_low:Q", title="Lift (treatment rate minus holdout rate)", axis=alt.Axis(format="%")
        ),
        x2="ci_high:Q",
    )
    points = base.mark_circle(size=90).encode(
        x="lift:Q", tooltip=["play_name", "lift", "p_value", "verdict"]
    )
    zero = alt.Chart(pd.DataFrame({"x": [0]})).mark_rule(strokeDash=[4, 4]).encode(x="x:Q")
    st.altair_chart(bars + points + zero, use_container_width=True)

st.subheader("One play in detail")
names = {play.name: play for play in catalog.plays}
play = names[st.selectbox("Play", list(names))]
row = results[results["play_id"] == play.id].iloc[0]
st.write(f"**Objective:** {play.objective}")
st.write(f"**Success metric:** {play.success_metric['description']}")
st.write(f"**Verdict:** {row['verdict']}  \n**Recommendation:** {row['recommendation']}")
if pd.notna(row["detectable_lift"]):
    st.caption(
        f"Smallest lift this sample could detect: about {row['detectable_lift']:.0%}. Split as designed: {'yes' if row['srm_ok'] else 'NO'}."
    )

left, right = st.columns(2)
with left:
    st.write("**Intervention ladder** (results by the highest rung an account reached)")
    ladder = ui.query(
        f"""
        SELECT highest_tier AS rung, accounts, successes
        FROM gold.metrics_play_ladder
        WHERE play_id = '{play.id}' AND metric = '{play.success_metric["id"]}'
        """
    )
    if len(ladder):
        ladder["rate"] = [
            ui.pct(s / a) for s, a in zip(ladder["successes"], ladder["accounts"], strict=True)
        ]
        st.dataframe(ladder, hide_index=True, width="stretch")
    for rung in play.intervention_ladder:
        st.caption(f"{rung.tier}: {rung.action} Move up when: {rung.move_up_when}")
with right:
    st.write("**Who got in, who was held out, who was kept out and why** (audit log)")
    audit = ui.rows(
        "SELECT decision, reason, count(*) AS accounts FROM audit_log WHERE play_id = :play "
        "GROUP BY decision, reason ORDER BY accounts DESC",
        play=play.id,
    )
    st.dataframe(audit, hide_index=True, width="stretch", height=280)
st.caption(f"Full specification: `docs/play-specs/{play.id}.md`")
