"""Human console: where people pick up what automation hands them. Synthetic data."""

import hmac
import json
import os
import re
from datetime import date

import streamlit as st

from app import ui
from app.events import customer_timeline
from common.config import load_yaml
from common.settings import load_settings
from engine.approvals import decide
from engine.catalog import load_catalog
from engine.handoff import resolve_cta
from integrations import crm_sync

# Which queues each role works. Admin sees everything.
ROLE_QUEUES = {
    "CSM": ["pooled_csm", "support", "admin_research", "human_review"],
    "Sales": ["sales"],
    "Admin": None,
}

st.title("Human console")
ui.job_intro("console")


def password_for(role: str) -> str | None:
    """Passwords come from the environment. On a laptop, "demo" works when none is set."""
    configured = os.environ.get(f"CONSOLE_PASSWORD_{role.upper()}")
    if configured:
        return configured
    return "demo" if load_settings().env == "dev" and not os.environ.get("DSO_HOSTED") else None


# Plain words for what the packet stores as codes.
REASONS = load_yaml("routing.yaml")["reason_codes"]
SIGNALS = {item["id"]: item["name"] for item in load_yaml("job.yaml")["signals"]}
SOURCES = {"agent": "the AI agent", "journey": "a play", "mailbox": "the shared mailbox"}


def show_task(task, packet: dict) -> None:
    """Draw one task as the person who receives it sees it: the handoff packet."""
    st.header(f"{task['title']}")
    reason = REASONS.get(task["reason_code"], task["reason_code"])
    st.caption(
        f"{packet['account_name']} ({task['account_id']}) | {reason} | priority: "
        f"{task['priority']} | due {task['sla_due_on']}"
    )

    left, right = st.columns(2)
    with left:
        st.subheader("Why this is on your desk")
        trigger = packet["trigger"]
        source = SOURCES.get(trigger.get("source"), trigger.get("source"))
        play = catalog.play(trigger["play"]).name if trigger.get("play") else None
        st.write(f"**From:** {source}" + (f", in the play {play}" if play else ""))
        if trigger.get("signal"):
            name = SIGNALS.get(trigger["signal"], trigger["signal"])
            st.write(f"**Signal:** {name}. {trigger.get('evidence') or ''}")
        else:
            # Not from a journey step (the agent or the mailbox handed off): show what is firing.
            firing = trigger.get("all_signals_firing") or {}
            listed = "; ".join(f"{SIGNALS.get(key, key)} ({why})" for key, why in firing.items())
            st.write(f"**Signals firing on the account:** {listed or 'none today'}.")
        if packet.get("customer_quote"):
            st.write("**In the customer's words:**")
            st.info(packet["customer_quote"])
        if packet.get("conversation_summary"):
            # The customer's words are quoted just above: do not repeat them here.
            summary = re.sub(r' The admin of .*? wrote: ".*?"', "", packet["conversation_summary"])
            st.write(f"**What happened with the agent:** {summary}")
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
        ui.metric(one, "Health", f"{health['score']:.0f}", health["band"], delta_color="off")
        ui.metric(
            two, "Seats", f"{snapshot['seats']['assigned']} of {snapshot['seats']['licensed']}"
        )
        ui.metric(three, "Renewal in", f"{snapshot['days_to_renewal']} days")
        if packet.get("brief"):
            st.subheader("Brief")
            st.text(packet["brief"])


def what_happens_next(task, result: dict) -> str:
    """The return signal in plain words: what the play does with the person's outcome."""
    if task["play_id"] and not task["enrollment_id"]:
        # A task beside the play (the Sales question on the Live demo): it does not move it.
        return (
            f"The play {catalog.play(task['play_id']).name} carries on: this task sits beside it."
        )
    if result["next_state"] == "sales_owns":
        return "Sales takes it from here, and the play stops sending messages."
    if not task["play_id"] or result["enrollment_status"] is None:
        return "This task was not a step of a play, so no play changes."
    play = catalog.play(task["play_id"])
    if result["enrollment_status"] == "exited":
        return f"The customer leaves the play {play.name}, which sends them nothing more."
    if result["enrollment_status"] == "completed":
        return f"The play {play.name} ends for this customer."
    enrollment = ui.store().one(
        "SELECT current_step FROM enrollments WHERE enrollment_id = :id", id=task["enrollment_id"]
    )
    journey = catalog.journeys[play.journey]
    if enrollment and journey.step(enrollment["current_step"]).type == "exit":
        return (
            f"The customer goes back to the play {play.name}. A person was its last step, so it "
            "closes for this customer on its next daily run, and the result counts against "
            "the holdout."
        )
    return f"The customer goes back into the play {play.name}, at its next step."


def complete_in_crm(cta_id: str, outcome: str, notes: str) -> str:
    """When live sends are on, mark the task completed in the CRM too (ADR 0032)."""
    if not crm_sync.live_enabled(ui.presenter()):
        return ""
    try:
        link = crm_sync.complete_task_now(cta_id, outcome, notes, data_dir=ui.data_dir())
    except Exception as error:  # another company's service: report it, never block the close
        return f" The CRM could not be updated: {str(error)[:200]}"
    if link is None:
        return " The CRM has no task for this handoff, so nothing was changed there."
    return " The task is marked completed in the CRM as well."


def show_approvals(queues: list[str] | None, role: str, today: str) -> None:
    """Drafts the system wrote that a person must approve before they are sent (ADR 0029)."""
    drafts = ui.rows("SELECT * FROM drafts WHERE status = 'pending' ORDER BY created_on, draft_id")
    if len(drafts) and queues:
        drafts = drafts[drafts["queue"].isin(queues)]
    st.subheader("Drafts waiting for approval")
    st.caption(
        "Some messages carry more risk than a setup guide, such as a request to act as a "
        "reference. The system writes them as drafts, and nothing is sent until a person "
        "approves. An approved draft is sent at the next daily run, after consent and the "
        "contact limit are checked again. A rejected draft ends the play for that customer."
    )
    if drafts.empty:
        st.caption("No draft is waiting for approval in your queues.")
        return
    names = dict(
        ui.query("SELECT account_id, account_name FROM gold.account_current").itertuples(
            index=False
        )
    )
    plays = {play.id: play.name for play in load_catalog().plays}
    for draft in drafts.itertuples():
        title = f"{names.get(draft.account_id, draft.account_id)}: {draft.subject}"
        with st.expander(f"{title} (written {draft.created_on})"):
            st.caption(
                f"Draft {draft.draft_id}, from the play {plays.get(draft.play_id, draft.play_id)}, "
                f"to {draft.recipient}."
            )
            st.markdown(draft.body)
            notes = st.text_input(
                "A note for the record (optional)", key=f"draft_note_{draft.draft_id}"
            )
            approve, reject = st.columns(2)
            choice = None
            if approve.button("Approve", key=f"approve_{draft.draft_id}", type="primary"):
                choice = True
            if reject.button("Reject", key=f"reject_{draft.draft_id}"):
                choice = False
            if choice is not None:
                decide(ui.store(), draft.draft_id, choice, today, role, notes)
                verdict = (
                    "approved. It will be sent at the next daily run"
                    if choice
                    else "rejected. The play ends for this customer"
                )
                st.session_state.console_message = f"Draft {draft.draft_id} {verdict}."
                ui.refresh()


if "console_role" not in st.session_state:
    st.write("Sign in to work on a queue. Each role sees only the queues it owns.")
    with st.form("login"):
        role = st.selectbox("Role", list(ROLE_QUEUES), help=ui.choices_help("Role"))
        password = st.text_input("Password", type="password")
        if st.form_submit_button("Sign in"):
            expected = password_for(role)
            if expected and hmac.compare_digest(password, expected):
                st.session_state.console_role = role
                st.rerun()
            st.error("The password is wrong, or this role has no password set.")
    if password_for("CSM") == "demo":
        st.caption(
            "In the local demo, the password for every role is `demo`. On the hosted demo, each "
            "role has its own password, set by the host."
        )
    # A visitor without a password still sees what a person receives: one task, read-only.
    example = ui.rows(
        "SELECT * FROM ctas ORDER BY CASE WHEN status <> 'resolved' THEN 0 ELSE 1 END, "
        "created_on DESC LIMIT 1"
    )
    if len(example):
        st.subheader("What a person receives: an example")
        st.caption(
            "This is one task from the demo, shown read-only. After you sign in, you can open "
            "the whole queue and close a task, which sends its outcome back to the play."
        )
        show_task(example.iloc[0], json.loads(example.iloc[0]["packet"]))
    # And one draft that waits for a person's approval, also read-only.
    st.subheader("A draft waiting for approval: an example")
    st.caption(
        "Some messages are sent only after a person approves them, such as a request to act "
        "as a reference. After you sign in as CSM or Admin, you can approve or reject them."
    )
    draft = ui.rows(
        "SELECT * FROM drafts ORDER BY status = 'pending' DESC, created_on DESC LIMIT 1"
    )
    if len(draft):
        with st.container(border=True):
            st.caption(f"Draft {draft.iloc[0]['draft_id']}, status: {draft.iloc[0]['status']}.")
            st.markdown(f"**Subject: {draft.iloc[0]['subject']}**")
            st.markdown(draft.iloc[0]["body"])
    else:
        st.caption("No draft has been written yet.")
    st.stop()

role = st.session_state.console_role
queues = ROLE_QUEUES[role]
catalog = load_catalog()
top_left, top_right = st.columns([5, 1])
team_names = [catalog.routing["queues"][queue]["name"] for queue in queues or []]
top_left.write(
    f"Signed in as **{role}**. "
    + (f"Queues: {', '.join(team_names)}." if team_names else "You see every team's queue.")
)
if top_right.button("Sign out"):
    del st.session_state.console_role
    st.rerun()

if "console_message" in st.session_state:
    st.success(st.session_state.pop("console_message"))
    closed = st.session_state.pop("closed_task", None)
    if closed and closed["play_id"]:
        # The return signal, made visible: the customer's path through the play, ending with
        # what the person just recorded and what the play did with it.
        play = catalog.play(closed["play_id"])
        st.markdown(f"**This customer's path through the play {play.name}:**")
        st.markdown(
            "\n".join(
                f"- {event['day']}: {event['text']}"
                for event in customer_timeline(ui.store(), closed["account_id"], play.id)
            )
        )

# The hosted demo is shared: whatever one visitor creates or closes, the next one sees.
# An admin can put it back to the state the image was built with.
if role == "Admin" and os.environ.get("DSO_HOSTED"):
    with st.expander("Admin: reset the demo data"):
        st.write(
            "This removes every task and conversation that visitors created or closed, and "
            "restores the demo's starting state. Use it before you give the demo to someone "
            "new."
        )
        if st.button("Reset the demo data"):
            from scripts.seed_store import seed

            st.session_state.console_message = "Demo data: " + seed(ui.data_dir(), reset=True)
            ui.refresh()

tasks = ui.rows("SELECT * FROM ctas WHERE status <> 'resolved' ORDER BY sla_due_on, created_on")
if len(tasks) and queues:
    tasks = tasks[tasks["queue"].isin(queues)]
today = ui.today()
alerts = ui.rows("SELECT * FROM queue_alerts ORDER BY alert_date DESC LIMIT 3")
if len(alerts) and (queues is None or alerts["queue"].isin(queues).any()):
    latest = alerts.iloc[0]
    st.warning(f"Capacity alert ({latest['alert_date']}): {latest['message']}")

show_approvals(queues, role, today)

st.subheader("Tasks in your queues")
if tasks.empty:
    st.success("Nothing is waiting in your queues.")
    st.caption(
        "To create a task here, open the Live demo page and select Run the story. The price "
        "question is passed to the Sales team."
    )
    st.stop()

order = {"urgent": 0, "high": 1, "normal": 2, "low": 3}
tasks = tasks.assign(rank=tasks["priority"].map(order), overdue=tasks["sla_due_on"] < today)
# Newest first, so a task just made on the Live demo is at the top of the list.
tasks = tasks.sort_values("cta_id", ascending=False)
st.caption(
    f"{len(tasks)} open tasks, the newest first (a task from the Live demo is at the top). "
    f"{int(tasks['overdue'].sum())} of them are past the date promised for a reply. "
    f"Today is {today}. In real life the Customer Success teams' tasks are CTAs in Gainsight, "
    "which this console plays, and the Sales queue is the Sales team's queue in "
    "Salesforce."
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

# The Live demo's button opens its new task here; forget it if this role cannot see it.
if st.session_state.get("open_task") not in set(tasks["cta_id"]):
    st.session_state.pop("open_task", None)
chosen = st.selectbox(
    "Open a task",
    tasks["cta_id"],
    index=None,
    placeholder="Choose a task to see it and close it",
    key="open_task",
)
if chosen is None:
    st.stop()
task = tasks[tasks["cta_id"] == chosen].iloc[0]
packet = json.loads(task["packet"])
show_task(task, packet)

st.subheader("Close the task")
st.caption(
    "The outcome you choose is sent back to the play. It decides whether the customer's "
    "journey resumes, ends, or passes to the Sales team."
)
outcomes = catalog.routing["outcomes"]
draft = packet.get("draft_reply")
with st.form("resolve"):
    # A handoff from the agent arrives with a reply drafted for the customer. The person
    # checks it, edits it, and is the one who sends it.
    reply = (
        st.text_area(
            "Reply to the customer (drafted for you: check, edit, send)", draft, height=170
        )
        if draft
        else None
    )
    # What each outcome means, and what the system does next, is in config/options.yaml:
    # on the question mark, and on each choice when the pointer rests on it.
    outcome = st.selectbox("Outcome", list(outcomes), help=ui.choices_help("Outcome"))
    notes = st.text_area("Notes", placeholder="What happened, in a sentence or two.")
    if st.form_submit_button("Send the reply and close" if draft else "Resolve"):
        if reply:  # the demo sends no email: the reply is kept with the outcome
            notes = f"{notes}\n\nReply sent to the customer:\n{reply}".strip()
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
            (f"{task['cta_id']}: reply sent and task closed. " if reply else "")
            + f"Outcome: {outcomes[outcome]['description'].lower()}. "
            + what_happens_next(task, result)
            + (
                " Saved as a draft evaluation case in evals/cases/from_feedback/."
                if outcome == "agent_should_have_handled"
                else ""
            )
            + complete_in_crm(task["cta_id"], outcome, notes)
        )
        st.session_state.closed_task = {
            "account_id": task["account_id"],
            "play_id": task["play_id"],
        }
        ui.refresh()
