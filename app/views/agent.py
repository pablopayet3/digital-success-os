"""Agents: what they said, what they looked up, when they handed off. Synthetic data."""

import json

import pandas as pd
import streamlit as st

from app import ui
from common.paths import ROOT

st.title("Agents")
st.write(
    "Two agents. The **onboarding agent** answers setup questions from the help centre and "
    "hands off when a hard rule says so. The **mailbox triage agent** reads every reply in the "
    "shared mailbox: a model labels it, rules decide what happens."
)

conversations = ui.rows("SELECT * FROM conversations ORDER BY day DESC, conversation_id DESC")
triage = ui.rows("SELECT * FROM mailbox_triage")
escalated = (
    conversations[conversations["outcome"] == "escalated"] if len(conversations) else conversations
)
one, two, three, four = st.columns(4)
one.metric("Agent conversations", len(conversations))
two.metric(
    "Handoff rate", ui.pct(len(escalated) / len(conversations)) if len(conversations) else "n/a"
)
three.metric("Mailbox replies triaged", len(triage))
four.metric(
    "LLM cost so far", f"${conversations['cost_usd'].sum():.2f}" if len(conversations) else "$0.00"
)

tab_conversations, tab_mailbox, tab_evals, tab_prompts = st.tabs(
    ["Conversations", "Mailbox triage", "Evaluation", "Prompts"]
)

with tab_conversations:
    if conversations.empty:
        st.info("No conversations yet. Simulate a day, or talk to the agent on the Live demo page.")
    else:
        left, right = st.columns(2)
        with left:
            st.write("**Why conversations were handed off**")
            reasons = escalated.groupby("reason_code").size().reset_index(name="handoffs")
            st.bar_chart(reasons, x="reason_code", y="handoffs", horizontal=True)
        with right:
            st.write("**Who decided to hand off**")
            st.caption(
                "hard_rule: code stopped it. agent: the model asked for a person. failure: a tool or the model was unavailable."
            )
            st.dataframe(
                escalated.groupby("escalated_by").size().reset_index(name="handoffs"),
                hide_index=True,
            )
        labels = {
            f"{row.conversation_id} | {row.day} | {row.scenario} | {row.outcome}{' (' + row.reason_code + ')' if row.reason_code else ''}": row.conversation_id
            for row in conversations.itertuples()
        }
        chosen = conversations[
            conversations["conversation_id"]
            == labels[st.selectbox("Open a conversation", list(labels))]
        ].iloc[0]
        for turn in json.loads(chosen["transcript"]):
            with st.chat_message("user" if turn["role"] == "customer" else "assistant"):
                st.write(turn["text"])
        if chosen["outcome"] == "escalated":
            st.warning(
                f"Handed off: {chosen['reason_code']} to queue {chosen['queue']} (decided by: {chosen['escalated_by']}). Task {chosen['cta_id']}."
            )
        with st.expander("What the agent did behind the answer"):
            st.write("Tool calls")
            st.json(json.loads(chosen["tool_calls"]))
            st.write("Help-centre searches and what they returned")
            st.json(json.loads(chosen["searches"]))
            st.caption(
                f"Prompt {chosen['prompt_version']} | {chosen['llm_calls']} model calls ({chosen['cached_llm_calls']} from cache) | ${chosen['cost_usd']:.4f} | trace file {chosen['trace_file']} (names and emails masked)"
            )

with tab_mailbox:
    if triage.empty:
        st.info("Nothing triaged yet.")
    else:
        st.write(
            "**What happened to each reply.** The model proposes an intent; `config/routing.yaml` decides the action."
        )
        st.dataframe(
            triage.groupby(["intent", "action"]).size().reset_index(name="replies"),
            hide_index=True,
            width="stretch",
        )
        st.caption(
            "An unsubscribe takes effect the same day. A complaint opens a high-priority task and pauses the account's emails. An unsure label goes to a person."
        )

with tab_evals:
    results_file = ROOT / "evals" / "reports" / "eval-results.json"
    if not results_file.exists():
        st.info("No evaluation yet. Run `uv run python run.py evals`.")
    else:
        results = json.loads(results_file.read_text(encoding="utf-8"))
        st.write(f"**Answers produced by:** {results['llm_mode']}")
        if "stand-in" in results["llm_mode"]:
            st.warning(
                "These results test the code around the model (rules, tools, routing). They say nothing about a real model's answers until one live run replaces them."
            )
        st.dataframe(
            pd.DataFrame(
                [{"suite": suite, **counts} for suite, counts in results["totals"].items()]
            ),
            hide_index=True,
            width="stretch",
        )
        accuracy = results.get("mailbox_accuracy")
        if accuracy and accuracy.get("scored"):
            st.write(
                f"**Mailbox classifier against the simulator's labels:** {ui.pct(accuracy['accuracy'])} on {accuracy['scored']} replies; {len(accuracy['costly_misses'])} costly misses (an unsubscribe or complaint read as something else)."
            )
            st.dataframe(pd.DataFrame(accuracy["matrix"]).T.fillna(0).astype(int), width="stretch")
        version = st.radio(
            "Agent cases, by prompt version", list(results["agent"]), horizontal=True
        )
        st.dataframe(
            pd.DataFrame(results["agent"][version])[
                ["id", "category", "status", "outcome", "reason_code", "judge_score"]
            ]
            if results["agent"][version] and "reason_code" in results["agent"][version][0]
            else pd.DataFrame(results["agent"][version]),
            hide_index=True,
            width="stretch",
        )
        st.caption("Full report: `evals/reports/eval-report.md`")

with tab_prompts:
    st.write(
        "Prompts are versioned like code. The changelog says what changed and why; the evals compare versions on the same cases."
    )
    st.markdown((ROOT / "prompts" / "CHANGELOG.md").read_text(encoding="utf-8"))
