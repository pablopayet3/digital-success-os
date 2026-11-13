"""Live demo: talk to the agent, watch it hand off, move the world forward a day."""

import os

import streamlit as st

from agents.llm import get_llm
from agents.onboarding import converse, scripted
from agents.runner import hand_off, record_conversation
from app import ui
from engine.catalog import load_catalog
from engine.context import load_day, records

# The two messages of the demo path: a setup question, then a question about price.
STORY = ["How do I invite my whole team at once?", "Thanks. How much would 10 more seats cost?"]
MAX_MESSAGE = 400  # characters a visitor may type in one message

st.title("Live demo")
ui.job_intro("demo")
tab_chat, tab_day = st.tabs(["Talk to the onboarding agent", "Advance one day"])

with tab_chat:
    st.write(
        "The whole loop on one account: a signal fires, it triggers a play, the play's agent "
        "talks to the admin, and a question the agent must not answer becomes a task for a "
        "person. You are the admin. A handoff creates a real task: open it in the Human console."
    )
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
    stalled = ui.query(
        """
        SELECT account_id, account_name, edition, prerequisite_closure_pct
        FROM gold.account_current
        WHERE coverage_tier = 'uncovered' AND prerequisite_closure_pct < 0.75 AND contacts_total > 0
        ORDER BY CASE WHEN signals_firing LIKE '%activation_stalled%' THEN 0 ELSE 1 END, account_id
        LIMIT 25
        """
    )  # accounts whose "setup stalled" signal is firing today come first
    labels = {
        f"{row.account_name} ({row.edition}, {row.prerequisite_closure_pct:.0%} set up)": row.account_id
        for row in stalled.itertuples()
    }
    account_id = labels[st.selectbox("You are the admin of", list(labels))]
    if st.session_state.get("demo_account") != account_id:
        st.session_state.demo_account, st.session_state.demo_messages = account_id, []
        st.session_state.pop("demo_task", None)

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
        ladder = " > ".join(rung.tier for rung in play.intervention_ladder)
        where = (
            "This page is the agent's rung of that ladder; a handoff is the next one."
            if with_agent
            else "That play has no agent rung. Below is what the agent says if this admin writes in."
        )
        enrolment = ui.store().one(
            "SELECT arm, status FROM enrollments WHERE account_id = :account AND play_id = :play "
            "ORDER BY enrolled_on DESC LIMIT 1",
            account=account_id,
            play=play.id,
        )
        if enrolment is None:
            in_play = "This account has not entered the play."
        elif enrolment["arm"] == "holdout":
            in_play = (
                "This account is **held out** of the play: the engine leaves it alone, to "
                "compare. If its admin writes in, the agent still answers."
            )
        else:
            in_play = f"This account is in the play (treatment; journey {enrolment['status']})."
        st.info(
            f"**Signal firing today:** `{signal}`. {evidence[signal]}\n\n"
            f"**Play it triggers:** {play.name} ({ladder}). {where}\n\n{in_play}"
        )
    else:
        st.caption("No signal is firing for this account today. The agent answers all the same.")

    with st.form("story"):
        st.write("**The scripted story.** One click, or edit the two messages first.")
        # Messages are kept short: on the public demo each one may be sent to a paid model.
        first = st.text_input("The admin asks", STORY[0], max_chars=MAX_MESSAGE)
        second = st.text_input("Then asks", STORY[1], max_chars=MAX_MESSAGE)
        run, _, over = st.columns([1, 4, 1])
        if run.form_submit_button("Run the story"):
            st.session_state.demo_messages = [first, second]
            st.session_state.pop("demo_task", None)
        if over.form_submit_button("Start over"):
            st.session_state.demo_messages = []
            st.session_state.pop("demo_task", None)

    st.caption(
        "Or type your own. Try: Where do I set up single sign-on? | How much are 10 more seats? | Can I talk to someone? | Does Relay do timesheets?"
    )
    if "offline" in get_llm().mode:
        st.caption(
            "Answers are replayed from stored model responses. The scripted story is stored "
            "for the first five accounts in the list, and the questions on the line above "
            "for the first one. A price or a request for a person never reaches the model, "
            "so those work everywhere. For anything else the agent says it is unavailable and "
            "hands off, which is the safe failure. To have a model answer anything you type, "
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
            escalation = conversation.escalation
            st.warning(
                f"Handed off to a person. Reason: **{escalation.reason_code}**. Queue: **{escalation.queue}**. "
                f"Decided by: **{conversation.escalated_by}**. Task **{st.session_state.demo_task}** is now in the Human console."
            )
            st.write(f"**Summary written for the person who picks it up:** {conversation.summary}")
        with st.expander("What the agent did behind the answer"):
            st.write("Tool calls")
            st.json(conversation.tool_calls)
            st.write("Help-centre searches (score, and whether an article covers the question)")
            st.json(conversation.searches)
            models = sorted({c["model"] for c in conversation.llm_log if c["role"] == "agent"})
            st.caption(
                f"Prompt {conversation.prompt_version}. Model calls: {len(conversation.llm_log)}. "
                f"Agent replies written by: {', '.join(models) or 'no agent model (a hard rule stopped it first)'}."
            )

with tab_day:
    st.write(
        "One simulated day: customers react to yesterday's touches, new telemetry lands, the "
        "pipeline rebuilds the tables, staff work their queues, the mailbox is triaged, the "
        "rules engine enrols accounts and the journeys deliver today's steps. About 30 seconds."
    )
    st.caption(f"Simulated today: {ui.today()}")
    if "offline" in get_llm().mode:
        st.caption(
            "Have the conversation on the other tab first. A new day changes the accounts, so "
            "the stored answers no longer match them and the agent will say it is unavailable."
        )
    if os.environ.get("DSO_HOSTED"):
        st.info(
            "Disabled in the hosted demo, which is read-only. Run it locally with `uv run python run.py run-day`."
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
