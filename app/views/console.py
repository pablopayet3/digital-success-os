"""Human console: where people pick up what automation hands them. Synthetic data."""

import hmac
import json
import os
from datetime import date

import streamlit as st

from app import ui
from common.settings import load_settings
from engine.catalog import load_catalog
from engine.handoff import resolve_cta

# Which queues each role works. Admin sees everything.
ROLE_QUEUES = {
    "CSM": ["pooled_csm", "support", "admin_research", "human_review"],
    "Sales": ["sales"],
    "Admin": None,
}

st.title("Human console")


def password_for(role: str) -> str | None:
    """Passwords come from the environment. On a laptop, "demo" works when none is set."""
    configured = os.environ.get(f"CONSOLE_PASSWORD_{role.upper()}")
    if configured:
        return configured
    return "demo" if load_settings().env == "dev" and not os.environ.get("DSO_HOSTED") else None


if "console_role" not in st.session_state:
    st.write("Sign in to work a queue. Each role sees the queues it owns.")
    with st.form("login"):
        role = st.selectbox("Role", list(ROLE_QUEUES))
        password = st.text_input("Password", type="password")
        if st.form_submit_button("Sign in"):
            expected = password_for(role)
            if expected and hmac.compare_digest(password, expected):
                st.session_state.console_role = role
                st.rerun()
            st.error("Wrong password, or this role has no password configured.")
    if password_for("CSM") == "demo":
        st.caption(
            "Local demo: the password for every role is `demo`. When hosted, passwords come from environment variables."
        )
    st.stop()

role = st.session_state.console_role
queues = ROLE_QUEUES[role]
catalog = load_catalog()
top_left, top_right = st.columns([5, 1])
top_left.write(f"Signed in as **{role}**. Queues: {', '.join(queues) if queues else 'all'}.")
if top_right.button("Sign out"):
    del st.session_state.console_role
    st.rerun()

if "console_message" in st.session_state:
    st.success(st.session_state.pop("console_message"))

tasks = ui.rows("SELECT * FROM ctas WHERE status <> 'resolved' ORDER BY sla_due_on, created_on")
if len(tasks) and queues:
    tasks = tasks[tasks["queue"].isin(queues)]
today = ui.today()
alerts = ui.rows("SELECT * FROM queue_alerts ORDER BY alert_date DESC LIMIT 3")
if len(alerts) and (queues is None or alerts["queue"].isin(queues).any()):
    latest = alerts.iloc[0]
    st.warning(f"Capacity alert ({latest['alert_date']}): {latest['message']}")

if tasks.empty:
    st.success("Nothing waiting in your queues.")
    st.stop()

order = {"urgent": 0, "high": 1, "normal": 2, "low": 3}
tasks = tasks.assign(rank=tasks["priority"].map(order), overdue=tasks["sla_due_on"] < today)
tasks = tasks.sort_values(["rank", "sla_due_on"])
st.caption(
    f"{len(tasks)} open tasks, most urgent first. {int(tasks['overdue'].sum())} past their SLA date. Today is {today}."
)
st.dataframe(
    tasks[
        [
            "cta_id",
            "priority",
            "queue",
            "reason_code",
            "title",
            "account_id",
            "source",
            "created_on",
            "sla_due_on",
            "overdue",
        ]
    ],
    hide_index=True,
    height=240,
    width="stretch",
)

task = tasks[tasks["cta_id"] == st.selectbox("Open a task", tasks["cta_id"])].iloc[0]
packet = json.loads(task["packet"])
st.header(f"{task['title']}")
st.caption(
    f"{packet['account_name']} ({task['account_id']}) | reason: {task['reason_code']} | priority: {task['priority']} | due {task['sla_due_on']}"
)

left, right = st.columns(2)
with left:
    st.subheader("Why this is on your desk")
    trigger = packet["trigger"]
    st.write(f"**Source:** {trigger.get('source')} | **Play:** {trigger.get('play') or 'none'}")
    st.write(f"**Signal:** {trigger.get('signal') or 'n/a'}. {trigger.get('evidence') or ''}")
    if packet.get("customer_quote"):
        st.write("**In the customer's words:**")
        st.info(packet["customer_quote"])
    if packet.get("conversation_summary"):
        st.write(f"**What happened with the agent:** {packet['conversation_summary']}")
    st.write("**What was already tried:**")
    for item in packet.get("what_was_tried") or ["Nothing yet."]:
        st.write(f"- {item}")
    st.success(f"**Recommended next step:** {packet['recommended_next_step']}")
    contact = packet.get("contact")
    if contact:
        st.write(
            f"**Contact:** {contact.get('full_name') or contact.get('name')} ({contact.get('role')}), {contact.get('email')}"
        )
with right:
    st.subheader("The account at a glance")
    snapshot = packet["account_snapshot"]
    health = snapshot["health"]
    one, two, three = st.columns(3)
    one.metric("Health", f"{health['score']:.0f}", health["band"], delta_color="off")
    two.metric("Seats", f"{snapshot['seats']['assigned']} of {snapshot['seats']['licensed']}")
    three.metric("Renewal in", f"{snapshot['days_to_renewal']} days")
    st.json(snapshot, expanded=False)
    if packet.get("brief"):
        st.subheader("Brief")
        st.text(packet["brief"])

st.subheader("Close the task")
st.caption(
    "Your outcome is the return signal: it decides whether the journey resumes, ends, or passes to Sales."
)
outcomes = catalog.routing["outcomes"]
with st.form("resolve"):
    outcome = st.selectbox(
        "Outcome",
        list(outcomes),
        format_func=lambda key: f"{key}: journey will {outcomes[key]['next_state']}",
    )
    notes = st.text_area("Notes", placeholder="What happened, in a sentence or two.")
    if st.form_submit_button("Resolve"):
        result = resolve_cta(
            ui.store(),
            catalog,
            task["cta_id"],
            outcome,
            date.fromisoformat(today),
            notes=notes,
            resolved_by=f"console:{role}",
            export_eval_case=True,
        )
        st.session_state.console_message = (
            f"{task['cta_id']} resolved as {outcome}. Journey: {result['next_state']}"
            + (
                f" (enrolment is now {result['enrollment_status']})."
                if result["enrollment_status"]
                else "."
            )
            + (
                " Saved as a draft evaluation case in evals/cases/from_feedback/."
                if outcome == "agent_should_have_handled"
                else ""
            )
        )
        ui.refresh()
