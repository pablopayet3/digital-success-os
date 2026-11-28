"""Live demo: talk to the agent, watch it hand off, move the world forward a day."""

import hmac
import json
import os
import re

import streamlit as st

from agents.llm import get_llm
from agents.onboarding import converse, scripted
from agents.runner import hand_off, record_conversation
from app import ui
from app.demo_story import STORY, first_customer, stalled_customers
from common.config import load_yaml
from engine.catalog import load_catalog
from engine.channels import render_template
from engine.context import load_day, records
from integrations import crm_sync

MAX_MESSAGE = 400  # characters a visitor may type in one message
# Who decided a handoff, and each team by its name, in plain words for the page.
DECIDED_BY = {
    "hard_rule": "a rule in code, before any AI model saw the message",
    "agent": "the AI agent",
    "failure": "a safety net, because the agent could not answer",
}
QUEUE_NAMES = {key: queue["name"] for key, queue in load_yaml("routing.yaml")["queues"].items()}
# The steps of a play's ladder, in plain words for the page.
LADDER_WORDS = {
    "digital": "an email first",
    "agentic": "the AI agent",
    "human": "a person",
}


def plain_evidence(evidence: str) -> str:
    """The evidence as a phrase: "Day 23: 2 of 4 ..." becomes "day 23 since signup, 2 of 4 ..."."""
    return re.sub(r"^Day (\d+): ", r"day \1 since signup, ", evidence)


def first_message(play, account_id: str, evidence: str, enrolment: dict | None) -> None:
    """Step 1 of a play: the message the system sends first, without being asked.

    The play is proactive. Without this, the page would open on the customer's question and
    look as if the customer had contacted us first.
    """
    steps = load_catalog().journeys[play.journey].steps
    opener = next((step for step in steps if step.type in ("email", "in_app")), None)
    if opener is None:
        return  # a play that goes straight to a person has no message to show
    account = records(
        ui.query(f"SELECT * FROM gold.account_current WHERE account_id = '{account_id}'")
    )[0]
    # Addressed to the customer's administrator, as the real message is.
    contacts = records(
        ui.query(
            f"SELECT full_name FROM gold.dim_contact WHERE account_id = '{account_id}' "
            "ORDER BY is_valid_admin DESC, contact_id LIMIT 1"
        )
    )
    contact = contacts[0] if contacts else None
    subject, body = render_template(opener.template, account, contact, evidence)
    sent = ui.store().one(
        "SELECT touch_date FROM touches WHERE account_id = :account AND play_id = :play "
        "AND template = :template ORDER BY touch_date LIMIT 1",
        account=account_id,
        play=play.id,
        template=opener.template,
    )
    if sent:
        note = f"Sent to this customer on {sent['touch_date']}, without anyone asking."
    elif enrolment and enrolment["arm"] == "holdout":
        note = "This customer is held out for comparison, so this message was not sent to them."
    else:
        note = "Sent as soon as the customer enters the play, without anyone asking."
    st.markdown("**Step 1. The system writes first.**")
    with st.container(border=True):
        st.caption(f"The play's first message. {note}")
        st.markdown(f"**Subject: {subject}**")
        st.markdown(body)


def presenter_sign_in() -> None:
    """On the hosted demo, the presenter signs in to send handoffs to the real CRM (ADR 0032).

    Shown only when the host has a CRM connection. A visitor without the password sees every
    step on screen and in the Human console; nothing they do reaches the CRM.
    """
    if not (os.environ.get("DSO_HOSTED") and os.environ.get(crm_sync.LIVE_SETTING) == "true"):
        return
    if ui.presenter():
        st.caption(
            "You are signed in as the presenter: the Sales task also goes to the real Salesforce."
        )
        return
    # Hidden from visitors: the presenter opens the page with ?presenter=1, or signs in to the
    # Human console as Admin, which turns presenter mode on as well.
    if st.query_params.get("presenter") != "1":
        return
    with st.expander("Presenter: also send handoffs to the real CRM"):
        st.caption(
            "Every visitor sees the whole story on this page and in the Human console. The "
            "presenter can also send the task to a real CRM, with the admin password."
        )
        with st.form("presenter"):
            password = st.text_input("Admin password", type="password")
            if st.form_submit_button("Sign in"):
                expected = os.environ.get("CONSOLE_PASSWORD_ADMIN")
                if expected and hmac.compare_digest(password, expected):
                    st.session_state.presenter = True
                    st.rerun()
                st.error("The password is wrong.")


def send_to_crm(task_id: str) -> dict | None:
    """Send the new task to the CRM at once, when live sends are on (ADR 0032).

    Returns what to show on screen. A failure is reported, never raised: the demo goes on.
    """
    if not crm_sync.live_enabled(ui.presenter()):
        return None
    with st.spinner("Sending the task to the CRM..."):
        try:
            return {"ok": True, **crm_sync.send_task_now(task_id, ui.data_dir())}
        except Exception as error:  # the CRM is another company's service: anything can fail
            return {"ok": False, "error": str(error)[:300]}


def create_tasks(account: dict, conversation, needs: list) -> list[dict]:
    """One task per team the customer needs, each with its draft reply.

    A task for the Customer Success team is the play's person step: it is linked to the
    customer's place in the play, so the outcome a person records moves the play on. Each
    task is written into the play's record of events, which the console shows afterwards.
    """
    store = ui.store()
    ctx = load_day(ui.data_dir(), store, load_catalog())
    account_id = account["account_id"]
    # The administrator, the person the play's first email went to (see first_message).
    contacts = sorted(
        ctx.contacts.get(account_id, []),
        key=lambda one: (not one.get("is_valid_admin"), one["contact_id"]),
    )
    contact = next(iter(contacts), None)
    # The customer's place in the play: the one under way, or else the latest one (the
    # customer has come back, so the play's person step picks the task up again).
    enrollment = store.one(
        "SELECT * FROM enrollments WHERE account_id = :account AND arm = 'treatment' "
        "ORDER BY CASE WHEN status IN ('active', 'waiting_on_human') THEN 0 ELSE 1 END, "
        "enrolled_on DESC LIMIT 1",
        account=account_id,
    )
    person_step = None
    if enrollment:
        journey = ctx.catalog.journeys[ctx.catalog.play(enrollment["play_id"]).journey]
        person_step = next(
            (
                step.id
                for step in journey.steps
                if step.type == "cta" and step.queue == "pooled_csm"
            ),
            None,
        )
    if enrollment:  # the conversation itself, as the journeys record an agent step
        store.insert(
            "journey_events",
            {
                "event_date": ctx.day,
                "enrollment_id": enrollment["enrollment_id"],
                "account_id": account_id,
                "play_id": enrollment["play_id"],
                "step_id": None,
                "event": "agent_escalated",
                "detail": "live_demo",
            },
        )
    tasks = []
    for need in needs:
        linked = need.queue == "pooled_csm" and person_step is not None
        task_id = hand_off(
            ctx,
            conversation,
            account,
            contact,
            enrollment=enrollment,  # every task carries the play's context
            step_id=person_step if linked else None,
            escalation=need,
        )
        if enrollment and not linked:
            # Context only: closing this task must not move the play, the CS task does that.
            store.update("ctas", {"cta_id": task_id}, enrollment_id=None)
        tasks.append({"id": task_id, "queue": need.queue, "why": need.why})
        if linked:  # the play now waits for the person, as at its own person step
            store.update(
                "enrollments",
                {"enrollment_id": enrollment["enrollment_id"]},
                status="waiting_on_human",
                current_step=person_step,
                exit_reason=None,
                closed_on=None,
            )
        if enrollment:
            store.insert(
                "journey_events",
                {
                    "event_date": ctx.day,
                    "enrollment_id": enrollment["enrollment_id"],
                    "account_id": account_id,
                    "play_id": enrollment["play_id"],
                    "step_id": person_step if linked else None,
                    "event": "cta_created",
                    "detail": f"{task_id} -> {need.queue}",  # as the journeys record it
                },
            )
    record_conversation(ctx, conversation, account, contact, None, "live_demo", tasks[0]["id"])
    return tasks


def where_it_lands(task: dict) -> str:
    """Where each task lands, as at a real company: a task for Sales in Salesforce, a CTA
    for Customer Success in Gainsight. The same handoff, named the way each tool names it."""
    if task["queue"] == "sales":
        label = crm_sync.crm_label(task["id"])
        if (st.session_state.get("demo_crm") or {}).get("ok"):
            return f"Task {label} is in Salesforce, in the Sales team's queue."
        return (
            f"Task {label} goes to the Sales team's queue in Salesforce. The public demo does "
            f"not send it, so here it waits in the Human console's Sales queue as {task['id']}."
        )
    team = QUEUE_NAMES.get(task["queue"], task["queue"])
    return (
        f"{task['id']} is a CTA in Gainsight, in the {team}'s queue (the Human console plays "
        "Gainsight here)."
    )


def show_handoff(conversation, tasks: list[dict]) -> None:
    """One box per team: who owns it, where it lands, and the reply drafted for them."""
    decided = DECIDED_BY.get(conversation.escalated_by, conversation.escalated_by)
    rows = ui.store().rows(
        "SELECT cta_id, packet FROM ctas WHERE cta_id IN ("
        + ", ".join(f"'{task['id']}'" for task in tasks)
        + ")"
    )
    drafts = {row["cta_id"]: json.loads(row["packet"]).get("draft_reply") for row in rows}
    for column, task in zip(st.columns(len(tasks)), tasks, strict=True):
        team = QUEUE_NAMES.get(task["queue"], task["queue"])
        with column:
            st.warning(
                f"**Handed to a person: {team}.** {task['why']}\n\n"
                f"Decided by {decided}. {where_it_lands(task)}"
            )
            if drafts.get(task["id"]):
                st.markdown("**Draft reply, ready for the person to check and send:**")
                with st.container(border=True):
                    st.text(drafts[task["id"]])
            if task["queue"] == "sales" and st.session_state.get("demo_crm"):
                show_crm_result(st.session_state.demo_crm)
            # Same tab, so a sign-in to the console is kept.
            if st.button("Open this task in the Human console", key=f"open_{task['id']}"):
                st.session_state.open_task = task["id"]
                st.switch_page("views/console.py")

    st.markdown("**Each person receives, with the task:**")
    missing = re.search(r"Setup still missing: (.*)\.$", conversation.summary or "")
    answered = sum(
        1
        for turn in conversation.transcript
        if turn["role"] == "agent" and turn.get("kind") != "handoff"
    )
    lines = [f'- **The customer wrote:** "{conversation.customer_quote}"']
    if conversation.escalated_by == "hard_rule" and missing:
        lines.append(
            f"- **Already answered by the agent:** {answered} earlier "
            f"{'question' if answered == 1 else 'questions'}"
        )
        lines.append(f"- **Setup still missing:** {missing.group(1)}")
    else:  # the agent wrote the summary itself: show it as it is
        lines.append(f"- **Summary:** {conversation.summary}")
    lines.append("- **The account at a glance:** health, seats, edition, renewal date, tickets")
    st.markdown("\n".join(lines))


def show_crm_result(crm: dict) -> None:
    if crm["ok"]:
        link = f" [Open it in the CRM]({crm['url']})." if crm.get("url") else ""
        st.success(
            "**The task is now in the CRM**, on the account, with the customer's own words "
            f"and the summary. The Sales team sees it in its queue.{link}"
        )
    else:
        st.warning(f"The task could not be sent to the CRM: {crm['error']}")


st.title("Live demo")
ui.job_intro("demo")
# The hosted demo is read-only, so it has no "Advance one day" tab and no tabs at all.
if os.environ.get("DSO_HOSTED"):
    tab_chat, tab_day = st.container(), None
else:
    tab_chat, tab_day = st.tabs(["Talk to the onboarding agent", "Advance one day"])

with tab_chat:
    # Real product names on this page at the owner's request (27 November 2026), as plain
    # text, the same exception as the guided tour.
    st.caption(
        "In real life: the customer data sits in Databricks, the play runs in Gainsight (the "
        "Human console plays that part here), a task for Customer Success is a CTA in "
        "Gainsight, and a task for Sales goes to Salesforce."
    )
    presenter_sign_in()
    llm = get_llm()
    if llm.settings.stand_in_when_unavailable:
        # The public demo with the real model: say what it may spend, and when that is gone.
        budget = llm.settings.llm_budget_usd
        if llm.limit_reached:
            st.warning(
                f"**The real model's budget for this public demo (${budget:.2f}) is used up.** "
                "From here on a labelled stand-in answers (keyword rules, not an AI model). "
                "The handoff rules are code, so they work exactly as before."
            )
        else:
            st.caption(
                f"A real AI model answers. Budget for this demo: ${budget:.0f}. "
                f"Used so far: ${llm.total_spent_usd:.2f}."
            )
    stalled = stalled_customers()  # "setup stalled" customers come first
    labels = {
        f"{row.account_name} ({row.edition}, {row.prerequisite_closure_pct:.0%} set up)": row.account_id
        for row in stalled.itertuples()
    }
    # Open on a customer who really received the play's first message: the story is clearer.
    start = first_customer(list(labels.values()))
    account_id = labels[st.selectbox("You are the admin of (select)", list(labels), index=start)]
    if st.session_state.get("demo_account") != account_id:
        st.session_state.demo_account, st.session_state.demo_messages = account_id, []
        st.session_state.pop("demo_tasks", None)
        st.session_state.pop("demo_crm", None)

    # Where this conversation sits in the loop: the signal, and the play it triggers.
    firing = ui.query(
        f"""
        SELECT signal_id, evidence FROM gold.signals
        WHERE account_id = '{account_id}'
          AND snapshot_date = (SELECT max(snapshot_date) FROM gold.signals)
        """
    )
    evidence = dict(zip(firing["signal_id"], firing["evidence"], strict=True))
    plays = [play for play in load_catalog().plays if set(play.trigger) & set(evidence)]
    # Several plays may be triggered: show one that has an agent rung, if there is one.
    with_agent = [p for p in plays if "agentic" in [rung.tier for rung in p.intervention_ladder]]
    if plays:
        play = min(with_agent or plays, key=lambda play: play.priority)
        signal = next(signal for signal in play.trigger if signal in evidence)
        ladder = ", then ".join(
            LADDER_WORDS.get(rung.tier, rung.tier) for rung in play.intervention_ladder
        )
        enrolment = ui.store().one(
            "SELECT arm, status FROM enrollments WHERE account_id = :account AND play_id = :play "
            "ORDER BY enrolled_on DESC LIMIT 1",
            account=account_id,
            play=play.id,
        )
        if enrolment is None:
            in_play = "**This customer:** not in the play yet."
        elif enrolment["arm"] == "holdout":
            in_play = "**This customer:** held out, so the play leaves it alone, for comparison."
        else:
            in_play = "**This customer:** in the play group, so it gets the play's help."
        # The signal by its plain name, as the Overview lists it.
        plain = {item["id"]: item["name"] for item in load_yaml("job.yaml")["signals"]}
        st.info(
            f"**Signal:** {plain.get(signal, signal).lower().rstrip('.')} "
            f"({plain_evidence(evidence[signal])}).\n\n"
            f"**Play:** {play.name}: {ladder}.\n\n{in_play}"
        )
        first_message(play, account_id, evidence[signal], enrolment)
    else:
        st.caption(
            "No signal is firing for this customer today. The agent still answers questions."
        )

    st.markdown("**Step 2. The customer replies to that message.**")
    with st.form("story"):
        st.write("**The scripted story.** Run it with one click, or edit the two messages first.")
        # Messages are kept short: on the public demo each one may be sent to a paid model.
        first = st.text_input("The customer replies", STORY[0], max_chars=MAX_MESSAGE)
        second = st.text_input("Then asks", STORY[1], max_chars=MAX_MESSAGE)
        run, _, over = st.columns([1, 4, 1])
        if run.form_submit_button("Run the story"):
            st.session_state.demo_messages = [first, second]
            st.session_state.pop("demo_tasks", None)
            st.session_state.pop("demo_crm", None)
        if over.form_submit_button("Start over"):
            st.session_state.demo_messages = []
            st.session_state.pop("demo_tasks", None)
            st.session_state.pop("demo_crm", None)

    st.caption(
        "Or type your own message. For example: Where do I set up single sign-on? How much "
        "are 10 more seats? Can I talk to someone? Does Relay do timesheets?"
    )
    if "offline" in get_llm().mode:
        st.caption(
            "Answers are replayed from stored responses of the real model. The scripted story "
            "is stored for the first five customers in the list, and the example questions "
            "above are stored for the first customer. A price question or a request for a "
            "person never reaches the model, so those work for every customer. For any other "
            "message, the agent says that it is unavailable and passes the customer to a "
            "person, which is the safe way to fail. To have the model answer anything you type, "
            "start the app with `uv run python run.py app --live`."
        )
    finished = "demo_tasks" in st.session_state
    message = st.chat_input("Your message to the agent", disabled=finished, max_chars=MAX_MESSAGE)
    if message:
        st.session_state.demo_messages.append(message)

    if st.session_state.demo_messages:
        account = records(
            ui.query(f"SELECT * FROM gold.account_current WHERE account_id = '{account_id}'")
        )[0]
        # The whole conversation is replayed on each message. Cached answers make that free.
        # A visible line while it runs, so a slow moment reads as the agent at work.
        with st.spinner("The agent is reading the help articles and checking the account..."):
            conversation = converse(account, scripted(st.session_state.demo_messages))
        for turn in conversation.transcript:
            with st.chat_message("user" if turn["role"] == "customer" else "assistant"):
                st.write(turn["text"])
        if conversation.outcome == "escalated":
            needs = [conversation.escalation, *conversation.more_escalations]
            if not finished:
                with st.spinner("Creating a task for each team, with the full context..."):
                    st.session_state.demo_tasks = create_tasks(account, conversation, needs)
                sales = [task for task in st.session_state.demo_tasks if task["queue"] == "sales"]
                st.session_state.demo_crm = send_to_crm(sales[0]["id"]) if sales else None
            show_handoff(conversation, st.session_state.demo_tasks)
        with st.expander("What the agent did behind the answer"):
            st.write("Tool calls")
            st.json(conversation.tool_calls)
            st.write(
                "Help center searches, with each score and whether an article covers the question"
            )
            st.json(conversation.searches)
            models = sorted({c["model"] for c in conversation.llm_log if c["role"] == "agent"})
            st.caption(
                f"Prompt {conversation.prompt_version}. Model calls: {len(conversation.llm_log)}. "
                f"Agent replies written by: {', '.join(models) or 'no agent model (a hard rule stopped it first)'}."
            )

if tab_day is not None:
    with tab_day:
        st.write(
            "One simulated day runs these steps in order. Customers react to yesterday's "
            "messages. New usage data arrives. The pipeline rebuilds the tables. Staff work on "
            "their queues. The shared mailbox is sorted. The rules put customers into plays. "
            "The journeys send the day's messages. It takes about 30 seconds."
        )
        st.caption(f"Simulated today: {ui.today()}")
        if "offline" in get_llm().mode:
            st.caption(
                "Have the conversation on the other tab first. A new day changes the customers' "
                "data, so the stored answers no longer match, and the agent will say that it is "
                "unavailable."
            )
        if os.environ.get("DSO_HOSTED"):
            st.info(
                "This is turned off in the hosted demo, which is read-only. To run it locally, use "
                "`uv run python run.py run-day`."
            )
        elif st.button("Advance one day"):
            from engine.run import run_day

            with st.spinner("The world moves, the pipeline runs, the engine acts..."):
                st.session_state.demo_day = run_day(ui.data_dir(), verbose=False)
            ui.refresh()
        if "demo_day" in st.session_state:
            summary = st.session_state.demo_day
            st.success(f"Simulated {summary['date']}.")
            keys = [
                "entered",
                "holdout",
                "excluded",
                "emails",
                "in_app",
                "agent_conversations",
                "ctas",
                "mailbox_replies_triaged",
                "resolved_by_staff",
                "goal_reached",
            ]
            for column, key in zip(st.columns(5) * 2, keys, strict=True):
                ui.metric(column, key.replace("_", " "), summary.get(key, 0))
