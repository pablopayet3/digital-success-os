"""Overview: the whole loop on one page. Synthetic data, fictional company."""

from datetime import date, timedelta

import altair as alt
import pandas as pd
import streamlit as st

from app import ui
from common.config import load_yaml
from common.paths import ROOT

# A task closed with one of these outcomes counts as a handoff that was worth making.
GOOD_OUTCOMES = ["resolved", "saved", "expansion_opportunity"]

st.title("Digital Success OS")
ui.what_this_is()
# For someone handed the link: a five-minute path through the whole loop.
guide = ROOT / "docs" / "reviewer-guide.md"
if guide.exists():
    with st.expander("First time here? Try the whole loop yourself in five minutes"):
        steps = guide.read_text(encoding="utf-8").splitlines()[1:]  # without the title line
        st.markdown("\n".join(steps))
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
ui.metric(one, "Accounts in the pilot", f"{int(accounts['accounts']):,}")
ui.metric(two, "ARR in the pilot", f"${accounts['arr'] / 1e6:.1f}M")
ui.metric(three, "Health: red", int(accounts["red"]))
in_play = (
    f"{ui.define('In a play now')} {held} more customers qualified and are deliberately "
    "left alone for comparison."
)
ui.metric(four, "In a play now", active, help=in_play)
ui.metric(five, "Tasks open for people", open_tasks)
# One short line under each number, in its own column.
one.caption("Customers with no assigned success manager")
two.caption("Annual recurring revenue: what these customers pay per year")
three.caption("Customers whose health score says they need attention")
four.caption("Customers currently receiving a prepared response")
five.caption("Handoffs waiting for a success manager or for Sales")

st.subheader("The measures the pilot is run on")
st.caption(
    "Each measure is defined once, with its formula and its source table, in "
    "`docs/metrics.md`. The first three cover every customer in the pilot. Only the last "
    "two compare customers in a play with customers deliberately left alone."
)


def usage_on(day: date) -> dict:
    """Usage of the pilot segment on one day, from the production table."""
    row = ui.query(
        f"""
        SELECT sum(mau_30d) AS mau, sum(assist_credits_30d) AS credits,
               avg(prerequisite_closure_pct) AS setup
        FROM gold.account_daily
        WHERE {in_pilot} AND snapshot_date = DATE '{day.isoformat()}'
        """
    ).iloc[0]
    return {key: 0.0 if pd.isna(value) else float(value) for key, value in row.items()}


def kpi(column, label: str, value: str, note: str) -> None:
    ui.metric(column, label, value)
    column.caption(note)


today = date.fromisoformat(ui.today())
now, before = usage_on(today), usage_on(today - timedelta(days=30))
conversations = ui.rows("SELECT account_id, outcome FROM conversations")
treated = ui.rows("SELECT DISTINCT account_id FROM enrollments WHERE arm = 'treatment'")
closed = ui.rows("SELECT outcome FROM ctas WHERE status = 'resolved'")
# Treated accounts that had at least one conversation with the agent.
talked = (
    len(set(conversations["account_id"]) & set(treated["account_id"]))
    if len(conversations) and len(treated)
    else 0
)
handed_off = int((conversations["outcome"] == "escalated").sum()) if len(conversations) else 0
good = closed["outcome"].isin(GOOD_OUTCOMES).sum() if len(closed) else 0

first = st.columns(4)
kpi(
    first[0],
    "Monthly active users",
    f"{now['mau']:,.0f}",
    f"People who used the product in the last 30 days. "
    f"{now['mau'] - before['mau']:+,.0f} against 30 days earlier",
)
kpi(
    first[1],
    "AI credits used, 30 days",
    f"{now['credits']:,.0f}",
    f"Use of the product's AI feature, in credits. "
    f"{now['credits'] - before['credits']:+,.0f} against 30 days earlier",
)
kpi(
    first[2],
    "Prerequisite closure",
    ui.pct(now["setup"]),
    f"Share of setup steps customers have completed. "
    f"{(now['setup'] - before['setup']) * 100:+.1f} points in 30 days",
)
kpi(
    first[3],
    "Agent invocation",
    ui.pct(talked / len(treated)) if len(treated) else "n/a",
    f"{talked} of the {len(treated)} customers in a play had a conversation with the AI "
    "agent. The others were helped by email alone, or have not reached that step",
)
second = st.columns(4)
kpi(
    second[0],
    "Handoff rate",
    ui.pct(handed_off / len(conversations)) if len(conversations) else "n/a",
    f"{handed_off} of {len(conversations)} agent conversations were passed to a person",
)
kpi(
    second[1],
    "Escalation conversion",
    ui.pct(good / len(closed)) if len(closed) else "n/a",
    f"{good} of {len(closed)} tasks handed to a person ended well: resolved, saved, or a "
    "sales opportunity",
)
try:
    money = ui.query("SELECT * FROM gold.experiment_results WHERE n_holdout > 0")
except Exception:  # results not built yet
    money = pd.DataFrame()
if money.empty:
    kpi(second[2], "Revenue retained", "n/a", "Run `uv run python run.py experiments`")
    kpi(second[3], "Expansion from the plays", "n/a", "Run `uv run python run.py experiments`")
else:
    kept = {
        arm: money[f"retained_arr_{arm}"].sum() / money[f"arr_at_entry_{arm}"].sum()
        for arm in ("treatment", "holdout")
    }
    kpi(
        second[2],
        "Revenue retained",
        ui.pct(kept["treatment"], 1),
        "Revenue still under contract 30 days after entering a play. Customers left alone "
        f"for comparison: {ui.pct(kept['holdout'], 1)}",
    )
    sales = money[money["metric"] == "expanded_30d"]
    won = {arm: sales[f"expansion_won_{arm}"].sum() for arm in ("treatment", "holdout")}
    each = {arm: won[arm] / max(sales[f"n_{arm}"].sum(), 1) for arm in ("treatment", "holdout")}
    kpi(
        second[3],
        "Expansion from the plays",
        f"${won['treatment']:,.0f}",
        f"New revenue from customers in a play: ${each['treatment']:,.0f} each, against "
        f"${each['holdout']:,.0f} for customers left alone",
    )

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
    "Customers with a signal": int(signals_today),
    "Entered a play": int(enrolments[enrolments["arm"] == "treatment"]["n"].sum())
    if len(enrolments)
    else 0,
    "Held out": held,
    "Touches delivered": int(ui.rows("SELECT count(*) AS n FROM touches")["n"][0]),
    "Agent conversations": int(ui.rows("SELECT count(*) AS n FROM conversations")["n"][0]),
    "Handed to a person": int(tasks["n"].sum()) if len(tasks) else 0,
    "Closed by a person": int(tasks[tasks["status"] == "resolved"]["n"].sum()) if len(tasks) else 0,
}
# Two rows, so that every label can be read in full.
slots = st.columns(4) + st.columns(4)
for column, (label, value) in zip(slots, counts.items(), strict=False):
    ui.metric(column, label, f"{value:,}")

left, right = st.columns(2)
with left:
    st.subheader("Health by coverage tier")
    st.caption(
        "A coverage tier is the level of human attention a customer receives. high_touch: a "
        "named success manager. pooled: a shared team of success managers. uncovered: no "
        "success manager. The pilot runs on the uncovered customers."
    )
    health = ui.query(
        "SELECT coverage_tier, health_band, count(*) AS accounts FROM gold.account_current "
        "GROUP BY coverage_tier, health_band"
    )
    # Health bands are drawn in their own colours: green must look green, red must look red.
    bands, colours = list(ui.BAND_COLOURS), list(ui.BAND_COLOURS.values())
    st.altair_chart(
        alt.Chart(health)
        .mark_bar()
        .encode(
            y=alt.Y("coverage_tier:N", title=None),
            x=alt.X("accounts:Q", title="accounts"),
            color=alt.Color(
                "health_band:N", title="health", scale=alt.Scale(domain=bands, range=colours)
            ),
            order=alt.Order("health_band:N"),
            tooltip=["coverage_tier", "health_band", "accounts"],
        ),
        use_container_width=True,
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
    # Plain names on the axis, and each signal's definition when the pointer is on its bar.
    meaning = {signal["id"]: signal for signal in load_yaml("job.yaml")["signals"]}
    firing["signal"] = [meaning.get(i, {}).get("name", i) for i in firing["signal_id"]]
    firing["it fires when"] = [meaning.get(i, {}).get("fires_when", "") for i in firing["signal_id"]]
    st.altair_chart(
        alt.Chart(firing)
        .mark_bar()
        .encode(
            y=alt.Y("signal:N", sort="-x", title=None, axis=alt.Axis(labelLimit=260)),
            x=alt.X("accounts:Q", title="customers"),
            tooltip=["signal", "it fires when", "accounts"],
        ),
        use_container_width=True,
    )
    st.caption("Point at a bar to read what the signal means.")

st.subheader("What the system did each day")
touches = ui.rows(
    "SELECT touch_date AS day, channel, count(*) AS touches FROM touches GROUP BY touch_date, channel"
)
if len(touches):
    st.bar_chart(touches, x="day", y="touches", color="channel")
else:
    st.info("No touches yet. Simulate a day on the Live demo page.")
