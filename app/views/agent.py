"""Agents: what they said, what they looked up, when they handed off. Synthetic data."""

import json
import os

import pandas as pd
import streamlit as st

from agents.review import rate_conversation
from app import ui
from common.paths import ROOT

st.title("Agents")
ui.job_intro("agent")
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
st.caption(
    "A conversation is one exchange between the onboarding agent and a customer. The handoff "
    "rate is the share of conversations the agent passed to a person. Mailbox replies are "
    "customers' answers to our emails, sorted by the triage agent. LLM cost is what the AI "
    "model charged for these conversations."
)

tab_conversations, tab_mailbox, tab_feedback, tab_evals, tab_review, tab_prompts = st.tabs(
    ["Conversations", "Mailbox triage", "Customer feedback", "Evaluation", "Review queue", "Prompts"]
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
        who = chosen.get("answered_by")
        who = who if isinstance(who, str) and who else "not recorded"
        st.caption(f"The agent's replies in this conversation were written by: **{who}**")
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

        st.write("**Was this conversation handled well?**")
        rated = chosen.get("feedback")
        if isinstance(rated, str) and rated:
            st.caption(f"Rated: thumbs {rated}.")
        if os.environ.get("DSO_HOSTED"):
            st.caption("Rating is switched off in the hosted demo, which is read-only.")
        else:
            notes = st.text_input(
                "For a thumbs down: what should have happened instead?",
                key=f"notes_{chosen['conversation_id']}",
            )
            up, down, _ = st.columns([1, 2, 4])
            if up.button("Thumbs up", key=f"up_{chosen['conversation_id']}"):
                rate_conversation(ui.store(), chosen["conversation_id"], True, notes, ui.today())
                ui.refresh()
            if down.button(
                "Thumbs down: send to the review queue", key=f"down_{chosen['conversation_id']}"
            ):
                rate_conversation(ui.store(), chosen["conversation_id"], False, notes, ui.today())
                ui.refresh()

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

with tab_feedback:
    st.write(
        "A score says how unhappy a customer is. The comment says why. A small model reads "
        "each recent NPS comment and high-priority ticket once and labels its sentiment and theme."
    )
    feedback = ui.rows(
        "SELECT kind, sentiment, theme, count(*) AS texts FROM text_classifications GROUP BY kind, sentiment, theme"
    )
    if feedback.empty:
        st.info("Nothing classified yet.")
    else:
        left, right = st.columns(2)
        with left:
            st.write("**What customers write about, and how they feel**")
            by_theme = feedback.groupby(["theme", "sentiment"], as_index=False)["texts"].sum()
            st.bar_chart(by_theme, x="theme", y="texts", color="sentiment", horizontal=True)
        with right:
            st.write("**What the unhappy ones are unhappy about**")
            negative = feedback[feedback["sentiment"] == "negative"]
            ranked = (
                negative.groupby("theme", as_index=False)["texts"]
                .sum()
                .sort_values("texts", ascending=False)
            )
            st.dataframe(ranked, hide_index=True, width="stretch")
            st.caption(
                "This is the list a play owner reads before writing the next play, and the list Product hears about."
            )
        st.caption(
            f"{int(feedback['texts'].sum())} texts classified: NPS comments and high-priority tickets from the last 30 days of each run."
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

with tab_review:
    st.write(
        "**The feedback loop.** A conversation lands here in two ways: a person closes a "
        "handoff as \"the agent should have handled this\" in the Human console, or a person "
        "gives a conversation a thumbs down on this page. Each row is a draft evaluation "
        "case. A person writes the expected behaviour, and the next prompt version has to pass it."
    )
    queue = ui.rows(
        "SELECT created_on, cta_id AS under_review, source, reason_code, human_notes "
        "FROM eval_candidates ORDER BY created_on DESC, cta_id DESC"
    )
    if queue.empty:
        st.info("Nothing is waiting for review.")
    else:
        st.caption(f"{len(queue)} waiting for review.")
        st.dataframe(queue, hide_index=True, width="stretch")

    st.write(
        "**The docs gap list.** Questions the agent handed to a person because no help "
        "article covered them. Each row is an article to write, or a decision that the "
        "product does not do this and the agent should say so."
    )
    unanswered = (
        conversations[conversations["reason_code"] == "not_in_docs"]
        if len(conversations)
        else conversations
    )
    if unanswered.empty:
        st.info("No question has fallen outside the help centre yet.")
    else:
        gaps = []
        for row in unanswered.itertuples():
            asked = [turn["text"] for turn in json.loads(row.transcript) if turn["role"] == "customer"]
            searches = json.loads(row.searches)
            closest = [result.get("title") for s in searches for result in s.get("results", [])]
            gaps.append(
                {
                    "day": row.day,
                    "account": row.account_id,
                    "the customer asked": asked[-1] if asked else "",
                    "the agent searched for": "; ".join(s.get("query", "") for s in searches),
                    "closest articles (not close enough)": ", ".join(filter(None, closest[:3])),
                }
            )
        st.dataframe(pd.DataFrame(gaps), hide_index=True, width="stretch")

with tab_prompts:
    st.write(
        "Prompts are versioned like code. The changelog says what changed and why; the evals compare versions on the same cases."
    )
    st.markdown((ROOT / "prompts" / "CHANGELOG.md").read_text(encoding="utf-8"))
