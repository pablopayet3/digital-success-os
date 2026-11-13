"""Pilot: is it ready, where is each play in its rollout, what happened each week.

Synthetic data, fictional company.
"""

import pandas as pd
import streamlit as st

from app import ui
from common.config import load_yaml
from common.paths import ROOT
from engine.catalog import load_catalog
from engine.context import load_day
from engine.pilot import readiness_checks, weekly_notes
from engine.rules import preview_segment

st.title("Pilot")
ui.job_intro("pilot")
segments = load_yaml("rollout.yaml")["segments"]
catalog = load_catalog()
st.write(
    "A pilot is a first trial on a limited group of customers, run to prove that the "
    "approach works before it is extended to the others. This pilot runs on one group of "
    f"customers: **{', '.join(segments)}**, the customers with no named success manager. "
    "Extending it to another group is then a change of configuration, not new software."
)

tiers = ui.query(
    "SELECT coverage_tier, count(*) AS accounts, sum(arr) AS arr, avg(health_score) AS avg_health "
    "FROM gold.account_current GROUP BY coverage_tier"
)
tiers["in_pilot"] = tiers["coverage_tier"].isin(segments)
st.dataframe(tiers, hide_index=True, width="stretch")

st.subheader("Readiness checklist")
st.caption(
    "Each line is checked against live data every time this page opens. Nobody ticks a "
    "box by hand. A play moves from a small slice of customers to a full test only when "
    "every line holds."
)
checks = readiness_checks(ui.data_dir())
ready = sum(check["passed"] for check in checks)
for check in checks:
    mark = ":green[**Ready**]" if check["passed"] else ":red[**Not ready**]"
    st.markdown(f"{mark} &nbsp; **{check['check']}.** {check['detail']}")
if ready == len(checks):
    st.success(f"All {len(checks)} checks hold today ({ui.today()}).")
else:
    st.warning(f"{ready} of {len(checks)} checks hold today ({ui.today()}). Fix the rest first.")

st.subheader("Rollout stage of each play")
st.caption(
    "A slice is 10% of the customers who qualify for a play. It confirms that nothing "
    "breaks. A full test covers every customer who qualifies, divided between those who "
    "receive the play and those held out for comparison."
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
    "Help is offered in this order: a digital message first, the AI agent next, and a "
    "person last. Each play is judged on its own measure of success. The customers who "
    "reach a person are the hardest cases, so their results cannot be compared with the "
    "others."
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
st.write("**What the last rung, a person, costs: tasks per queue**")
st.dataframe(handoffs, hide_index=True, width="stretch")

st.subheader("Handoff quality")
st.caption(
    "A handoff is worth making only if a person picks it up in time and it ends well. Hover "
    "over a number for its definition."
)
quality = ui.query(
    """
    SELECT sum(handoffs) AS handoffs, sum(closed) AS closed, sum(picked_up) AS picked_up,
           sum(days_to_pickup_total) AS days, sum(sla_breaches) AS late,
           sum(converted) AS converted, sum(unnecessary) AS unnecessary,
           sum(recontacted) AS recontacted,
           sum(CASE WHEN source = 'agent' THEN handoffs ELSE 0 END) AS from_agent,
           sum(CASE WHEN source = 'agent' AND reason_code = 'not_in_docs' THEN handoffs ELSE 0 END)
               AS docs_gaps
    FROM gold.metrics_handoffs
    """
).iloc[0]


def share(part, whole) -> str:
    return ui.pct(part / whole) if whole else "n/a"


measures = {
    "Time to pickup": (
        f"{quality['days'] / quality['picked_up']:.1f} days" if quality["picked_up"] else "n/a",
        f"average over {int(quality['picked_up'] or 0)} tasks picked up",
    ),
    "SLA breach rate": (
        share(quality["late"], quality["handoffs"]),
        f"{int(quality['late'] or 0)} of {int(quality['handoffs'] or 0)} picked up late or still open past due",
    ),
    "Escalation conversion": (
        share(quality["converted"], quality["closed"]),
        "closed as resolved, saved or an opportunity",
    ),
    "Unnecessary handoffs": (
        share(quality["unnecessary"], quality["closed"]),
        "closed as: the agent should have handled this",
    ),
    "Re-contact": (
        share(quality["recontacted"], quality["closed"]),
        "a new task for the same account within 14 days of one closing",
    ),
    "Docs gap share": (
        share(quality["docs_gaps"], quality["from_agent"]),
        f"of {int(quality['from_agent'] or 0)} agent handoffs: no help article covered the question",
    ),
}
for column, (label, (value, note)) in zip(st.columns(6), measures.items(), strict=True):
    ui.metric(column, label, value)
    column.caption(note)

st.subheader("Weekly review notes")
st.caption(
    "This table has one row for each week of the pilot. A fixed rule writes each note "
    "from the numbers, so the note cannot flatter the result. In a real review, the "
    "owners of the plays add the decisions they took."
)
notes = pd.DataFrame(weekly_notes(ui.data_dir()))
if notes.empty:
    st.info("Nothing has run yet. Simulate a day on the Live demo page.")
else:
    notes.columns = [column.replace("_", " ") for column in notes.columns]
    st.dataframe(notes, hide_index=True, width="stretch")

st.subheader("How the pattern scales")
st.markdown(
    "1. **Slice.** A new play starts on 10% of the customers who qualify (`rollout_stage: slice`). The question at this stage is whether anything breaks, not whether the play works.\n2. **Full test.** Every qualifying customer in the pilot takes part, and half of them are held out. The question is whether the play improves the measure named before launch.\n3. **Next group.** Add `pooled` to `config/rollout.yaml`. The same plays, rules and safeguards then run for those customers, and a test in the repository proves it. The holdout drops to 10% and stays there.\n4. **Change control.** Each step is a reviewed change to a configuration file, with the experiment report attached (`docs/change-control.md`)."
)


@st.cache_data(ttl=60, show_spinner=False)
def scaling_preview(segment: str, today: str) -> list[dict]:
    """Today's rules run on one more segment, writing nothing. (`today` keeps the cache honest.)"""
    return preview_segment(load_day(ui.data_dir(), ui.store(), load_catalog()), segment)


for segment in [tier for tier in ("pooled",) if tier not in segments]:
    preview = pd.DataFrame(scaling_preview(segment, ui.today()))
    st.write(f"**Preview: what adding `{segment}` would do today**")
    st.caption(
        "This applies the same rules today to one more group of customers, without changing "
        "anything. It shows the first day only. The later steps of each play add more tasks "
        "in the weeks that follow."
    )
    shown = preview.drop(columns="play_id").rename(columns=lambda name: name.replace("_", " "))
    st.dataframe(shown, hide_index=True, width="stretch")
    queues = catalog.routing["queues"]
    first_day = preview.dropna(subset=["first_day_queue"]).groupby("first_day_queue")["would_enter"]
    for queue, tasks in first_day.sum().items():
        capacity = queues[queue]["capacity_per_day"]
        line = (
            f"{queues[queue]['name']}: {int(tasks)} new tasks on the first day, for a team "
            f"that can handle {capacity} a day."
        )
        if tasks > capacity:
            st.warning(
                f"{line} That is more than a day of work. Start with a slice, or add people first."
            )
        else:
            st.write(f":green[**The team can handle it.**] &nbsp; {line}")

plan = ROOT / "docs" / "pilot-plan.md"
if plan.exists():
    with st.expander("The pilot plan"):
        st.markdown(plan.read_text(encoding="utf-8"))
