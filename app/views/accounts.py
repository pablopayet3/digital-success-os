"""Accounts: one account, everything known about it. Synthetic data, fictional company."""

import json

import pandas as pd
import streamlit as st

from app import ui

st.title("Accounts")

tier, stage, band = st.columns(3)
tiers = tier.multiselect(
    "Coverage tier", ["uncovered", "pooled", "high_touch"], default=["uncovered"]
)
stages = stage.multiselect(
    "Lifecycle stage", ["onboarding", "adopting", "mature", "expansion", "renewal", "at_risk"]
)
bands = band.multiselect("Health band", ["green", "yellow", "red"])

accounts = ui.query(
    """
    SELECT account_id, account_name, coverage_tier, segment, edition, lifecycle_stage,
           health_score, health_band, churn_risk_score, expansion_score, arr,
           seats_assigned, seats_licensed, signals_firing
    FROM gold.account_current ORDER BY health_score
    """
)
shown = accounts[accounts["coverage_tier"].isin(tiers or accounts["coverage_tier"].unique())]
if stages:
    shown = shown[shown["lifecycle_stage"].isin(stages)]
if bands:
    shown = shown[shown["health_band"].isin(bands)]
st.caption(f"{len(shown):,} accounts. Sorted by health, lowest first.")
st.dataframe(shown, hide_index=True, height=260, width="stretch")

if shown.empty:
    st.stop()
labels = {f"{row.account_name} ({row.account_id})": row.account_id for row in shown.itertuples()}
account_id = labels[st.selectbox("Open an account", list(labels))]
account = ui.query(f"SELECT * FROM gold.account_current WHERE account_id = '{account_id}'").iloc[0]

st.header(account["account_name"])
st.caption(
    f"{account['segment']} | {account['edition']} edition | {account['coverage_tier']} | "
    f"lifecycle: {account['lifecycle_stage']} | ARR ${account['arr']:,.0f} | "
    f"renewal in {account['days_to_renewal']} days"
)
one, two, three, four = st.columns(4)
one.metric("Health", f"{account['health_score']:.0f}", account["health_band"], delta_color="off")
two.metric("Churn risk", ui.pct(account["churn_risk_score"]))
three.metric("Expansion likelihood", ui.pct(account["expansion_score"]))
four.metric("Seats", f"{account['seats_assigned']} of {account['seats_licensed']}")

left, right = st.columns(2)
with left:
    st.subheader("Why the health score is what it is")
    components = pd.DataFrame(
        {
            "component": ["adoption", "engagement", "sentiment", "support", "commercial"],
            "score": [
                account[f"health_{name}"]
                for name in ("adoption", "engagement", "sentiment", "support", "commercial")
            ],
        }
    )
    st.bar_chart(components, x="component", y="score", horizontal=True)
    st.write(f"**Churn model says:** {account['churn_top_reasons'] or 'nothing stands out'}")
    st.write(
        f"**Expansion model says:** {account['expansion_top_reasons'] or 'nothing stands out'}"
    )
with right:
    st.subheader("Signals firing today")
    signals = ui.query(
        f"""
        SELECT signal_id, evidence FROM gold.signals
        WHERE account_id = '{account_id}'
          AND snapshot_date = (SELECT max(snapshot_date) FROM gold.account_current)
        """
    )
    if len(signals):
        st.dataframe(signals, hide_index=True, width="stretch")
    else:
        st.write("None.")
    steps = {
        "has_first_board": "First board",
        "has_five_users": "Five users",
        "has_integration": "Integration",
        "has_sso": "Single sign-on",
    }
    st.write(
        "**Setup:** "
        + ", ".join(
            f"{label} {'done' if account[column] else 'missing'}" for column, label in steps.items()
        )
    )

st.subheader("The last 90 days")
history = ui.query(
    f"""
    SELECT snapshot_date, health_score, mau_30d, seats_assigned
    FROM gold.account_daily WHERE account_id = '{account_id}'
    ORDER BY snapshot_date DESC LIMIT 90
    """
).sort_values("snapshot_date")
first, second = st.columns(2)
first.line_chart(history, x="snapshot_date", y="health_score")
second.line_chart(history, x="snapshot_date", y=["mau_30d", "seats_assigned"])

st.subheader("What the system did, and why")
plays = ui.rows(
    "SELECT enrolled_on, play_id, arm, status, exit_reason, trigger_evidence, highest_tier FROM enrollments WHERE account_id = :id ORDER BY enrolled_on",
    id=account_id,
)
touches = ui.rows(
    "SELECT touch_date, play_id, channel, tier, subject, outcome FROM touches WHERE account_id = :id ORDER BY touch_date",
    id=account_id,
)
tasks = ui.rows(
    "SELECT created_on, queue, reason_code, title, status, outcome FROM ctas WHERE account_id = :id ORDER BY created_on",
    id=account_id,
)
audit = ui.rows(
    "SELECT run_date, play_id, decision, reason FROM audit_log WHERE account_id = :id ORDER BY run_date DESC LIMIT 40",
    id=account_id,
)
for label, frame in (("Plays", plays), ("Touches", touches), ("Tasks for people", tasks)):
    st.write(f"**{label}**")
    if len(frame):
        st.dataframe(frame, hide_index=True, width="stretch")
    else:
        st.caption("None.")
with st.expander(
    "Audit log: every decision about this account, including why it was NOT put in a play"
):
    st.dataframe(audit, hide_index=True, width="stretch")
with st.expander("Raw row from gold.account_current"):
    st.json(json.loads(account.to_json(date_format="iso")))
