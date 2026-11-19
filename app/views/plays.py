"""Plays and experiments: what runs, for whom, and whether it works. Synthetic data."""

import altair as alt
import pandas as pd
import streamlit as st

from app import ui
from app.journey_canvas import journey_dot, step_counts
from common.config import load_yaml
from engine.catalog import load_catalog
from engine.journeys import journey_funnel

KINDS = {"email": "Email", "in-app": "Message in the product", "agent": "AI agent",
         "cta": "Task for a person"}  # fmt: skip
ENDINGS = {"completed": "Finished", "exited": "Left early", "active": "Still running",
           "waiting_on_human": "Waiting for a person", "holdout": "Held out"}  # fmt: skip


def words(code: str) -> str:
    """A configuration code as words: "no_longer_stalled" becomes "no longer stalled"."""
    text = str(code).replace("_", " ").replace("human: ", "a person recorded: ")
    return text.replace("csm ", "success manager ")


def plain_reason(reason: str) -> str:
    """An audit reason in words: "signal activation_stalled" names the signal."""
    if reason.startswith("signal "):
        code = reason.removeprefix("signal ")
        names = {item["id"]: item["name"] for item in load_yaml("job.yaml")["signals"]}
        return f"its signal fired: {names.get(code, words(code)).lower()}"
    return words(reason)


def plain_stage(stage: str) -> str:
    """A funnel step such as "email: setup_guide (digital)" as "Email: setup guide"."""
    kind, _, rest = stage.partition(": ")
    if kind in KINDS:
        return f"{KINDS[kind]}: {words(rest.split(' (')[0])}"
    return stage


st.title("Plays and experiments")
ui.job_intro("plays")
catalog = load_catalog()

st.subheader("The play catalog")
st.caption(
    "Each play is a few lines of configuration, not software. The system enforces three "
    "rules for every play: the customer has agreed to be contacted, no customer is "
    "contacted more than twice a week, and a share of customers is held out for comparison."
)
# Plain words for the configuration's codes, so the table reads without a key. A plain
# table (st.table) wraps long text instead of cutting it off.
SIGNAL_NAMES = {item["id"]: item["name"] for item in load_yaml("job.yaml")["signals"]}
RUNGS = {"digital": "Digital message", "agentic": "AI agent", "human": "A person"}
STAGES = {"slice": "10% slice", "full": "Full test"}
st.table(
    pd.DataFrame(
        [
            {
                "Play": play.name,
                "Starts when": " or ".join(SIGNAL_NAMES.get(s, s) for s in play.trigger),
                "Help, in order": " → ".join(RUNGS[rung.tier] for rung in play.intervention_ladder),
                "Stage": STAGES.get(play.rollout_stage, play.rollout_stage),
                "Held out": f"{play.holdout_pct:.0%}",
                "Measure of success": play.success_metric["description"],
                "Owner": play.owner,
            }
            for play in sorted(catalog.plays, key=lambda play: play.priority)
        ]
    ).set_index("Play")
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
    f"As of {results['as_of'][0]}. The customers are simulated, so any improvement shown here "
    "comes from the simulation's assumptions. The method of measurement is what a real "
    "pilot would use."
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
measures = {play.id: play.success_metric["description"] for play in catalog.plays}
st.table(
    pd.DataFrame(
        {
            "Play": table["play_name"],
            "Measure": [measures.get(play_id, "") for play_id in table["play_id"]],
            "In the play": table["treatment"],
            "Held out": table["holdout"],
            "Difference": table["lift"],
            "Chance it is luck (p)": table["p"],
            "Verdict": table["verdict"],
        }
    ).set_index("Play")
)
st.caption(
    "In the play and Held out: the share of customers who reached the measure, with the "
    "counts. Difference: the first minus the second. Chance it is luck (p): how likely a "
    "difference this large would be if the play did nothing; below 0.05 is usually read as "
    "real. The recommendation for each play is under One play in detail."
)

measured = results.dropna(subset=["lift"])
if len(measured):
    st.write(
        "**The improvement on each play's measure of success, with its margin of error.** "
        "Lift is the difference between the customers in the play and the customers held "
        "out. When the margin crosses zero, the play may have had no effect."
    )
    base = alt.Chart(measured).encode(y=alt.Y("play_name:N", title=None, sort=None))
    # Colours are set by hand so the interval and the zero line show on a dark page too.
    bars = base.mark_errorbar(color="#6f9bd1", thickness=2).encode(
        x=alt.X(
            "ci_low:Q", title="Lift (treatment rate minus holdout rate)", axis=alt.Axis(format="%")
        ),
        x2="ci_high:Q",
    )
    points = base.mark_circle(size=90, color="#6f9bd1").encode(
        x="lift:Q", tooltip=["play_name", "lift", "p_value", "verdict"]
    )
    zero = (
        alt.Chart(pd.DataFrame({"x": [0]}))
        .mark_rule(strokeDash=[4, 4], color="#9aa0a6")
        .encode(x="x:Q")
    )
    st.altair_chart(bars + points + zero, use_container_width=True)

st.subheader("One play in detail")
names = {play.name: play for play in catalog.plays}
# Open on the play with the most rungs in its ladder: it shows the whole pattern.
longest = max(catalog.plays, key=lambda play: len(play.intervention_ladder))
play = names[st.selectbox("Play", list(names), index=list(names).index(longest.name))]
found = results[results["play_id"] == play.id]
row = found.iloc[0] if len(found) else None  # a new play has no result yet
st.write(f"**Objective:** {play.objective}")
st.write(f"**Success metric:** {play.success_metric['description']}")
if row is None:
    st.write("**Verdict:** no customer has finished this play yet, so there is no result.")
else:
    st.write(f"**Verdict:** {row['verdict']}  \n**Recommendation:** {row['recommendation']}")

# The journey drawn from the same configuration that runs it (app/journey_canvas.py).
st.write("**The journey, drawn**")
st.caption(
    "Read it from top to bottom: the signal that starts the play, who may enter, the share "
    "held out for comparison, then each step. Blue is a digital message, purple is the AI "
    "agent, orange is a person. Each step says how many customers reached it."
)
arms = {
    item["arm"]: item["n"]
    for item in ui.rows(
        "SELECT arm, count(*) AS n FROM enrollments WHERE play_id = :play GROUP BY arm",
        play=play.id,
    ).to_dict("records")
}
signal_names = {item["id"]: item["name"] for item in load_yaml("job.yaml")["signals"]}
st.graphviz_chart(
    journey_dot(
        play,
        catalog.journeys[play.journey],
        catalog.routing["queues"],
        signal_names,
        step_counts(ui.store(), play.id),
        arms,
    ),
    use_container_width=False,  # its natural size, readable; the box scrolls sideways
)
if row is not None and pd.notna(row["detectable_lift"]):
    st.caption(
        f"The smallest improvement this number of customers could reveal: about "
        f"{row['detectable_lift']:.0%}. Customers divided between the two groups as designed: "
        f"{'yes' if row['srm_ok'] else 'NO'}."
    )

left, right = st.columns(2)
with left:
    st.write("**Journey funnel** (the number of customers who reached each step)")
    funnel = pd.DataFrame(journey_funnel(ui.store(), catalog.journeys[play.journey], play.id))
    funnel["stage"] = [plain_stage(stage) for stage in funnel["stage"]]
    st.altair_chart(
        alt.Chart(funnel)
        .mark_bar()
        .encode(
            y=alt.Y("stage:N", sort=None, title=None, axis=alt.Axis(labelLimit=320)),
            x=alt.X("accounts:Q", title="accounts"),
            tooltip=["stage", "accounts"],
        ),
        use_container_width=True,
    )
    st.caption(
        "Counted from the journey's own record of events. A customer can skip a step, so a "
        "later step is not always smaller than the one before it."
    )
with right:
    st.write("**How the journeys ended**")
    endings = ui.rows(
        "SELECT status, coalesce(exit_reason, 'still running') AS reason, count(*) AS accounts "
        "FROM enrollments WHERE play_id = :play AND arm = 'treatment' "
        "GROUP BY status, exit_reason ORDER BY accounts DESC",
        play=play.id,
    )
    st.table(
        pd.DataFrame(
            {
                "How it ended": [
                    ENDINGS.get(status, words(status)) for status in endings["status"]
                ],
                "Why": [words(reason) for reason in endings["reason"]],
                "Customers": endings["accounts"],
            }
        ).set_index("How it ended")
    )

left, right = st.columns(2)
with left:
    st.write(
        "**Results by the week customers entered** (so that one unusual week cannot hide in "
        "the average)"
    )
    try:
        weeks = ui.query(
            f"SELECT * FROM gold.experiment_cohorts WHERE play_id = '{play.id}' ORDER BY week_starting"
        )
    except Exception:  # a warehouse built before this table existed
        weeks = pd.DataFrame()
    if weeks.empty:
        st.caption("No weekly group of customers has been observed for long enough yet.")
    else:
        st.dataframe(
            pd.DataFrame(
                {
                    "week starting": weeks["week_starting"],
                    "treatment": [
                        f"{ui.pct(r)} of {n}" if n else "none"
                        for r, n in zip(weeks["rate_treatment"], weeks["n_treatment"], strict=True)
                    ],
                    "holdout": [
                        f"{ui.pct(r)} of {n}" if n else "none"
                        for r, n in zip(weeks["rate_holdout"], weeks["n_holdout"], strict=True)
                    ],
                }
            ),
            hide_index=True,
            width="stretch",
        )
with right:
    st.write("**Revenue in the 30 days after entry**")
    if row is None or "arr_at_entry_treatment" not in results.columns or not row["n_holdout"]:
        st.caption("This play has no holdout to compare with.")
    else:
        groups = {"treatment": "In the play", "holdout": "Held out"}
        st.table(
            pd.DataFrame(
                [
                    {
                        "Group": groups[arm],
                        "Customers": int(row[f"n_{arm}"]),
                        "Revenue at entry": f"${row[f'arr_at_entry_{arm}']:,.0f}",
                        "Revenue kept": ui.pct(
                            row[f"retained_arr_{arm}"] / row[f"arr_at_entry_{arm}"], 1
                        )
                        if row[f"arr_at_entry_{arm}"]
                        else "n/a",
                        "Still a customer": ui.pct(row[f"still_customer_{arm}"]),
                        "Expansion won": f"${row[f'expansion_won_{arm}']:,.0f}",
                    }
                    for arm in ("treatment", "holdout")
                ]
            ).set_index("Group")
        )
        st.caption(
            '"Still a customer" is the safeguard that every play is checked against. A play '
            "that improves its own measure but loses customers is not working."
        )

left, right = st.columns(2)
with left:
    st.write("**The ladder of help** (results by the highest step a customer reached)")
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
        st.table(
            pd.DataFrame(
                {
                    "Highest step reached": [
                        RUNGS.get(rung, "Nothing yet") for rung in ladder["rung"]
                    ],
                    "Customers": ladder["accounts"],
                    "Reached the measure": [int(n) for n in ladder["successes"]],
                    "Share": ladder["rate"],
                }
            ).set_index("Highest step reached")
        )
    for rung in play.intervention_ladder:
        st.caption(f"{RUNGS[rung.tier]}: {rung.action} Move up when: {rung.move_up_when}")
with right:
    st.write("**Who entered, who was held out, who was kept out, and why** (from the audit log)")
    audit = ui.rows(
        "SELECT decision, reason, count(*) AS accounts FROM audit_log WHERE play_id = :play "
        "GROUP BY decision, reason ORDER BY accounts DESC",
        play=play.id,
    )
    decisions = {"entered": "Entered", "holdout": "Held out", "excluded": "Kept out"}
    st.table(
        pd.DataFrame(
            {
                "Decision": [decisions.get(d, words(d)) for d in audit["decision"]],
                "Reason": [plain_reason(reason or "") for reason in audit["reason"]],
                "Customers": audit["accounts"],
            }
        )
        .head(8)
        .set_index("Decision")
    )
st.caption(f"Full specification: `docs/play-specs/{play.id}.md`")
