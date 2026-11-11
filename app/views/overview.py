"""Overview: the whole loop on one page. Synthetic data, fictional company."""

import streamlit as st

from app import ui
from common.config import load_yaml

st.title("Digital Success OS")
st.write(
    "Customer signals become plays. A play is a journey, an AI agent, or a task for a "
    "person. When the agent cannot help it hands off with full context, and the person's "
    "outcome comes back into the system. Every play is measured against a holdout."
)
segments = load_yaml("rollout.yaml")["segments"]
in_pilot = "coverage_tier IN (" + ", ".join(f"'{s}'" for s in segments) + ")"
st.caption(f"Simulated today: {ui.today()}. Pilot segment: {', '.join(segments)}.")

accounts = ui.query(
    f"""
    SELECT count(*) AS accounts, sum(arr) AS arr,
           sum(CASE WHEN health_band = 'red' THEN 1 ELSE 0 END) AS red
    FROM gold.account_current WHERE {in_pilot}
    """
).iloc[0]
enrolments = ui.rows("SELECT arm, status, count(*) AS n FROM enrollments GROUP BY arm, status")
tasks = ui.rows("SELECT status, count(*) AS n FROM ctas GROUP BY status")
active = (
    int(enrolments[enrolments["status"].isin(["active", "waiting_on_human"])]["n"].sum())
    if len(enrolments)
    else 0
)
held = int(enrolments[enrolments["arm"] == "holdout"]["n"].sum()) if len(enrolments) else 0
open_tasks = int(tasks[tasks["status"] != "resolved"]["n"].sum()) if len(tasks) else 0

one, two, three, four, five = st.columns(5)
one.metric("Accounts in the pilot", f"{int(accounts['accounts']):,}")
two.metric("ARR in the pilot", f"${accounts['arr'] / 1e6:.1f}M")
three.metric("Health: red", int(accounts["red"]))
four.metric("In a play now", active, help=f"{held} more are held out for comparison")
five.metric("Tasks open for people", open_tasks)

st.subheader("From signal to outcome")
signals_today = ui.query(
    f"""
    SELECT count(DISTINCT signals.account_id) AS n
    FROM gold.signals AS signals
    JOIN gold.account_current AS accounts ON signals.account_id = accounts.account_id
    WHERE signals.snapshot_date = accounts.snapshot_date AND accounts.{in_pilot}
    """
)["n"][0]
counts = {
    "Accounts with a signal today": int(signals_today),
    "Entered a play (treatment)": int(enrolments[enrolments["arm"] == "treatment"]["n"].sum())
    if len(enrolments)
    else 0,
    "Held out": held,
    "Touches delivered": int(ui.rows("SELECT count(*) AS n FROM touches")["n"][0]),
    "Agent conversations": int(ui.rows("SELECT count(*) AS n FROM conversations")["n"][0]),
    "Handed to a person": int(tasks["n"].sum()) if len(tasks) else 0,
    "Closed by a person": int(tasks[tasks["status"] == "resolved"]["n"].sum()) if len(tasks) else 0,
}
for column, (label, value) in zip(st.columns(len(counts)), counts.items(), strict=True):
    column.metric(label, f"{value:,}")

left, right = st.columns(2)
with left:
    st.subheader("Health by coverage tier")
    health = ui.query(
        "SELECT coverage_tier, health_band, count(*) AS accounts FROM gold.account_current "
        "GROUP BY coverage_tier, health_band"
    )
    st.bar_chart(
        health,
        x="coverage_tier",
        y="accounts",
        color="health_band",
        horizontal=True,
    )
with right:
    st.subheader("Signals firing today (pilot segment)")
    firing = ui.query(
        f"""
        SELECT signals.signal_id, count(*) AS accounts
        FROM gold.signals AS signals
        JOIN gold.account_current AS accounts ON signals.account_id = accounts.account_id
        WHERE signals.snapshot_date = accounts.snapshot_date AND accounts.{in_pilot}
        GROUP BY signals.signal_id ORDER BY accounts DESC
        """
    )
    st.bar_chart(firing, x="signal_id", y="accounts", horizontal=True)

st.subheader("What the system did each day")
touches = ui.rows(
    "SELECT touch_date AS day, channel, count(*) AS touches FROM touches GROUP BY touch_date, channel"
)
if len(touches):
    st.bar_chart(touches, x="day", y="touches", color="channel")
else:
    st.info("No touches yet. Simulate a day on the Live demo page.")
