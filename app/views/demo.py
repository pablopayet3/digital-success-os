"""Live demo: talk to the agent, watch it hand off, move the world forward a day."""

import os

import streamlit as st

from agents.onboarding import converse, scripted
from agents.runner import hand_off, record_conversation
from app import ui
from engine.catalog import load_catalog
from engine.context import load_day, records

st.title("Live demo")
tab_chat, tab_day = st.tabs(["Talk to the onboarding agent", "Advance one day"])

with tab_chat:
    st.write(
        "You are the admin of a customer whose setup has stalled. Ask how to do something "
        "(the agent answers from the help centre), then try a price, a refund, or asking for a "
        "person. A handoff creates a real task: open it in the Human console."
    )
    stalled = ui.query(
        """
        SELECT account_id, account_name, edition, prerequisite_closure_pct
        FROM gold.account_current
        WHERE coverage_tier = 'uncovered' AND prerequisite_closure_pct < 0.75 AND contacts_total > 0
        ORDER BY account_id LIMIT 25
        """
    )
    labels = {
        f"{row.account_name} ({row.edition}, {row.prerequisite_closure_pct:.0%} set up)": row.account_id
        for row in stalled.itertuples()
    }
    account_id = labels[st.selectbox("You are the admin of", list(labels))]
    if st.session_state.get("demo_account") != account_id:
        st.session_state.demo_account, st.session_state.demo_messages = account_id, []
        st.session_state.pop("demo_task", None)
    if st.button("Start over"):
        st.session_state.demo_messages = []
        st.session_state.pop("demo_task", None)

    st.caption(
        "Try: How do I invite my whole team at once? | Where do I set up single sign-on? | How much are 10 more seats? | Can I talk to someone? | Does Relay do timesheets?"
    )
    finished = "demo_task" in st.session_state
    message = st.chat_input("Your message to the agent", disabled=finished)
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
            column.metric(key.replace("_", " "), summary.get(key, 0))
