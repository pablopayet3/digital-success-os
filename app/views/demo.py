"""Live demo: talk to the agent, watch it hand off, move the world forward a day."""

import hmac
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
            "ORDER BY is_valid_admin DESC LIMIT 1"
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
        st.caption("Presenter mode: a handoff on this page is also sent to the real CRM.")
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


def show_crm_result(crm: dict) -> None:
    if crm["ok"]:
        link = f" [Open it in the CRM]({crm['url']})." if crm.get("url") else ""
        st.success(
            "**The task is now in the CRM**, on the account, with the customer's own words "
            f"and the summary. The account owner sees it in their own task list.{link}"
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
        "At a real company: the data in Databricks, the play in Gainsight (the Human console "
        "stands in for its task list), the Sales task in Salesforce."
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
                f"The real model answers here. This public demo may spend ${budget:.2f} on it "
                f"in total. Used so far: ${llm.total_spent_usd:.2f}."
            )
    stalled = stalled_customers()  # "setup stalled" customers come first
    labels = {
        f"{row.account_name} ({row.edition}, {row.prerequisite_closure_pct:.0%} set up)": row.account_id
        for row in stalled.itertuples()
    }
    # Open on a customer who really received the play's first message: the story is clearer.
    start = first_customer(list(labels.values()))
    account_id = labels[st.selectbox("You are the admin of", list(labels), index=start)]
    if st.session_state.get("demo_account") != account_id:
        st.session_state.demo_account, st.session_state.demo_messages = account_id, []
        st.session_state.pop("demo_task", None)
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
            f"**Why:** {plain.get(signal, signal).lower().rstrip('.')} "
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
            st.session_state.pop("demo_task", None)
            st.session_state.pop("demo_crm", None)
        if over.form_submit_button("Start over"):
            st.session_state.demo_messages = []
            st.session_state.pop("demo_task", None)
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
    finished = "demo_task" in st.session_state
    message = st.chat_input("Your message to the agent", disabled=finished, max_chars=MAX_MESSAGE)
    if message:
        st.session_state.demo_messages.append(message)

    if st.session_state.demo_messages:
        account = records(
            ui.query(f"SELECT * FROM gold.account_current WHERE account_id = '{account_id}'")
        )[0]
        # The whole conversation is replayed on each message. Cached answers make that free.
        conversation = converse(account, scripted(st.session_state.demo_messages))
        for turn in conversation.transcript:
            with st.chat_message("user" if turn["role"] == "customer" else "assistant"):
                st.write(turn["text"])
        if conversation.outcome == "escalated":
            if not finished:
                ctx = load_day(ui.data_dir(), ui.store(), load_catalog())
                contact = next(iter(ctx.contacts.get(account_id, [])), None)
                task_id = hand_off(ctx, conversation, account, contact)
                record_conversation(ctx, conversation, account, contact, None, "live_demo", task_id)
                st.session_state.demo_task = task_id
                st.session_state.demo_crm = send_to_crm(task_id)
            escalation = conversation.escalation
            team = QUEUE_NAMES.get(escalation.queue, escalation.queue)
            decided = DECIDED_BY.get(conversation.escalated_by, conversation.escalated_by)
            st.warning(
                f"**Handed to a person: {team}.** {escalation.why}\n\n"
                f"Decided by {decided}. Task {st.session_state.demo_task} is waiting in the "
                "Human console."
            )
            st.markdown(f"**What {team} receives with the task:**")
            missing = re.search(r"Setup still missing: (.*)\.$", conversation.summary or "")
            if conversation.escalated_by == "hard_rule" and missing:
                answered = sum(1 for turn in conversation.transcript if turn["role"] == "agent")
                st.markdown(
                    f'- **The customer wrote:** "{conversation.customer_quote}"\n'
                    f"- **Already answered by the agent:** {answered} earlier "
                    f"{'question' if answered == 1 else 'questions'}\n"
                    f"- **Setup still missing:** {missing.group(1)}\n"
                    f"- **Suggested next step:** {conversation.recommended_next_step}"
                )
            else:  # the agent wrote the summary itself: show it as it is
                st.markdown(
                    f"- **Summary:** {conversation.summary}\n"
                    f"- **Suggested next step:** {conversation.recommended_next_step}"
                )
            crm = st.session_state.get("demo_crm")
            if crm:
                show_crm_result(crm)
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
