"""Ask the data: Claude answers questions about the data and the program, typed or spoken.

Synthetic data, fictional company. See ADR 0028, agents/assistant.py and
app/assistant_voice.html.
"""

import json
import os
from pathlib import Path

import streamlit as st

from agents.assistant import Answer, ask, examples
from agents.llm import get_llm
from app import ui
from common.config import load_yaml

VOICE_PAGE = (Path(__file__).parent.parent / "assistant_voice.html").read_text(encoding="utf-8")
MAX_QUESTION = 400  # characters a visitor may type in one question


def api_url() -> str:
    """Where the browser finds the API, which starts voice sessions and answers for the voice."""
    if os.environ.get("DSO_API_URL"):
        return os.environ["DSO_API_URL"].rstrip("/")
    urls = load_yaml("assistant.yaml")["api_url"]
    return urls["hosted"] if os.environ.get("DSO_HOSTED") else urls["local"]


def voice_settings() -> dict:
    """What the voice script needs: the service's settings and the voice's instructions."""
    voice = load_yaml("assistant.yaml")["voice"]
    instructions = " ".join(
        [
            "You are the voice of a data assistant for the Digital Success OS, a working model",
            "of a customer-success operation built on synthetic data for a fictional company,",
            "Lumen Labs, whose product is Relay. You only speak; Claude finds the answers.",
            "For every question about the customers, the data, the plays, the AI agents, the",
            "teams or how the program is run, call ask_claude with the person's question in",
            "full, and wait for its answer. Never answer such a question from your own",
            "knowledge, and never make up a number. While you wait, say a few real words, such",
            "as 'Let me look at the data.' When the answer arrives, say it briefly and",
            "naturally, in two or three sentences, and keep its key numbers. Never read a",
            "table, a list or a source line aloud: say that the full answer is on the screen.",
            "Lead with the answer. When you have finished, stop: do not offer more help.",
            "If the person interrupts you, stop at once and deal with what they said.",
            "Use contractions, plain words and short sentences. Never open with 'okay',",
            "'great' or 'got it'. Never name a real company or product.",
            voice["style"].strip(),
        ]
    )
    return {
        "apiUrl": api_url(),
        "model": voice["model"],
        "voice": voice["voice"],
        "transcriptionModel": voice["transcription_model"],
        "idleMinutes": voice["idle_minutes"],
        "maxMinutes": voice["max_minutes"],
        "instructions": instructions,
        "opening": (
            "Greet the person in one short sentence. Say that you can answer questions about "
            "the customers, the plays and the teams of this demo, and invite a question."
        ),
    }


def show(answer: Answer) -> None:
    """One question and its answer, with how the answer was found."""
    with st.chat_message("user"):
        st.write(answer.question)
    with st.chat_message("assistant"):
        st.markdown(answer.text)
        if answer.stored:
            st.caption(
                "This is a stored answer. Claude wrote it once from this demo's data, so the "
                "example questions cost nothing and always work."
            )
        elif answer.available and answer.model:
            st.caption(f"Written just now by {answer.model}.")
        if answer.sql or answer.documents:
            with st.expander("How the answer was found"):
                for statement in answer.sql:
                    st.code(statement, language="sql")
                if answer.documents:
                    st.write("Documents read: " + ", ".join(f"`{d}`" for d in answer.documents))


def answer_and_keep(question: str) -> None:
    with st.spinner("Claude is reading the data. This can take up to half a minute."):
        st.session_state.ask_history.append(ask(question, ui.data_dir()))


st.title("Ask the data")
ui.job_intro("ask")
st.session_state.setdefault("ask_history", [])

st.write(
    "Ask a question about the customers, the plays, the AI agent or the way each team works. "
    "Claude, an AI model, answers it. It reads the warehouse with read-only queries and "
    "searches the program's documents, and every number in its answer comes from that data. "
    "Under each answer, you can open the queries and the documents it used."
)

st.subheader("Talk to the assistant")
st.caption(
    "The voice works like a phone call: it listens all the time, answers out loud, and stops "
    "as soon as you speak over it. A voice service listens and speaks, and Claude finds each "
    "answer. Your browser will ask for permission to use the microphone."
)
# No "<" may reach the script: the HTML cleaner would delete it (see the HTML file).
settings_json = json.dumps(voice_settings()).replace("<", "\\u003c")
with st.container(key="dso_voice"):  # the voice panel is drawn inside this container
    st.html(VOICE_PAGE.replace("__CONFIG__", settings_json), unsafe_allow_javascript=True)

st.subheader("Example questions, by team")
st.caption("Each team asks questions like these every week. Select one to see Claude's answer.")
for team, questions in examples().items():
    st.markdown(f"**{team}**")
    for column, question in zip(st.columns(len(questions)), questions, strict=True):
        if column.button(question, key=f"example-{question}", width="stretch"):
            answer_and_keep(question)

st.subheader("Answers")
llm = get_llm()
if "stand-in" in llm.mode or "offline" in llm.mode:
    st.caption(
        "Here, only the example questions have answers, because no AI model is connected for "
        "new questions. On the hosted demo, the real model answers new questions when its host "
        "has provided a key, within a spending limit."
    )
if not st.session_state.ask_history:
    st.info("Select an example question above, or type your own question below.")
for answer in st.session_state.ask_history:
    show(answer)

typed = st.chat_input("Ask your own question about the data", max_chars=MAX_QUESTION)
if typed:
    answer_and_keep(typed)
    st.rerun()
