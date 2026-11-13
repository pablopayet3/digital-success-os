"""The guided tour: a small window in a corner that explains the app one element at a time.

Synthetic data, fictional company. Each stop is one metric or one section. The window says
what it is and how to read it, and the element it is about is outlined on the page and
scrolled into view. The window sits in a corner, so it never covers what it explains.

The words are in config/tour.yaml. The window's look and the outline are in
app/tour_card.html (a style and a short script). This file moves from stop to stop.

A stop can be read aloud: scripts/tour_voice.py records each stop once, and the window
offers "Read aloud" for every stop that has a recording.

On the hosted demo the tour starts by itself. Locally it starts from the button in the
sidebar, so a live demo is never interrupted.

Where the tour is: `tour_step` in the session is the stop's number, or None when no tour
is running.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import streamlit as st

from app import ui
from common.config import load_yaml

CARD = (Path(__file__).parent / "tour_card.html").read_text(encoding="utf-8")
AUDIO = Path(__file__).parent / "tour_audio"  # recordings made by scripts/tour_voice.py
# What the script in the card may be told about a stop (see app/tour_card.html).
FIND = ("target", "tab", "expand", "group")


def stops() -> list[dict]:
    return load_yaml("tour.yaml")["stops"]


def spoken(stop: dict) -> str:
    """What the recorded voice says for one stop: exactly the words in the window."""
    parts = [stop["title"], stop["what"], "Who uses it.", stop["who"]]
    parts += ["For example.", stop["example"]]
    sentences = [part.strip() for part in parts]
    return " ".join(s if s.endswith((".", "?")) else s + "." for s in sentences)


def audio_file(stop: dict) -> Path:
    """Where the recording of a stop lives. The name is a fingerprint of the words, so a
    stop whose words have changed has no recording until it is recorded again."""
    return AUDIO / f"{hashlib.sha256(spoken(stop).encode()).hexdigest()[:16]}.mp3"


def show(current_page: str) -> None:
    """Draw the sidebar button, and the tour's window when a tour is running."""
    state = st.session_state
    if "tour_step" not in state:
        # A visitor of the hosted demo is greeted by the first stop. Locally, nothing opens.
        state.tour_step = 0 if os.environ.get("DSO_HOSTED") else None
    state.tour_page = current_page
    if st.sidebar.button("Guided tour", width="stretch"):
        _go(0)
    if state.tour_step is None:
        if state.pop("tour_ended", False):
            _draw_script({})  # take the outline off the last element
        return
    # The visitor may have used the menu: the tour then follows them to that page.
    names = [ui.PAGE_NAMES[stop["page"]] for stop in stops()]
    if names[state.tour_step] != current_page and current_page in names:
        state.tour_step = names.index(current_page)
    _window(state.tour_step)


def _go(index: int) -> None:
    """Move to a stop, and to its page when that is another page."""
    state = st.session_state
    state.tour_step = index
    page = stops()[index]["page"]
    if ui.PAGE_NAMES[page] == state.get("tour_page"):
        st.rerun()
    st.switch_page(f"views/{page}.py")


def _end() -> None:
    st.session_state.tour_step = None
    st.session_state.tour_ended = True
    st.rerun()


def _window(index: int) -> None:
    all_stops = stops()
    stop, last = all_stops[index], index == len(all_stops) - 1
    with st.container(key="tour_card"):
        st.caption(
            f"Guided tour · {ui.PAGE_NAMES[stop['page']]} · stop {index + 1} of {len(all_stops)}"
        )
        st.markdown(f"**{stop['title']}**")
        st.markdown(stop["what"].strip())
        st.markdown(f"**Who uses it.** {stop['who'].strip()}")
        st.markdown(f"**For example.** {stop['example'].strip()}")
        recording = audio_file(stop)
        if recording.exists() and st.toggle("Read aloud", key="tour_voice_on"):
            st.audio(str(recording), autoplay=True)
        back, forward = st.columns(2)
        if back.button("Back", disabled=index == 0, width="stretch"):
            _go(index - 1)
        if forward.button("Finish" if last else "Next", type="primary", width="stretch"):
            if last:
                _end()
            _go(index + 1)
        if st.button("End the tour", type="tertiary", width="stretch"):
            _end()
        # Scroll to the element only when the stop has changed, not on every redraw.
        moved = st.session_state.get("tour_drawn") != index
        st.session_state.tour_drawn = index
        _draw_script({**{key: stop.get(key) for key in FIND}, "scroll": moved})


def _draw_script(find: dict) -> None:
    """Put the card's style and script on the page, told what to outline."""
    told = json.dumps(find).replace("</", "<\\/")  # safe inside a script tag
    st.html(CARD.replace("__STOP__", told), unsafe_allow_javascript=True)
