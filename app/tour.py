"""The guided tour: pop-up windows that walk a visitor through the app, one Next at a time.

Synthetic data, fictional company. The words are in config/tour.yaml; this file only
shows them. Each window opens on the page it explains and says four things: what the
visitor is looking at, which tool and team do this at a real company, what the role asks
for, and what the person in the role does.

How it behaves:
  - On the hosted demo the first window opens by itself, once per visit. Locally the
    tour starts from the button in the sidebar, so a live demo is never interrupted.
  - Next and Back move between windows and switch to the right page.
  - A window can be closed to look at the page behind it. A thin bar at the top of the
    page then offers to reopen it, go on, or end the tour.

Where the tour is: two values in the session, `tour_step` (the window's number, or None
when no tour is running) and `tour_open` (is the window showing).
"""

from __future__ import annotations

import os

import streamlit as st

from common.config import load_yaml

# What each part of a window is called on screen, in the order shown.
PARTS = {
    "look": "What you are looking at.",
    "company": "At a real company.",
    "job": "What the role asks for.",
    "mine": "My part in it.",
}


def steps() -> list[dict]:
    return load_yaml("tour.yaml")["steps"]


def show() -> None:
    """Draw the tour: the sidebar button, and the window or the bar when a tour is running."""
    state = st.session_state
    if "tour_step" not in state:
        # A visitor of the hosted demo is greeted by the first window. Locally, nothing opens.
        state.tour_step = 0 if os.environ.get("DSO_HOSTED") else None
        state.tour_open = True
    if st.sidebar.button("Guided tour (3 minutes)", width="stretch"):
        _go(0)
    if state.tour_step is None:
        return
    if state.tour_open:
        _window(state.tour_step)
    else:
        _bar(state.tour_step)


def _go(index: int) -> None:
    """Move to a window and to the page it explains."""
    st.session_state.tour_step, st.session_state.tour_open = index, True
    st.switch_page(f"views/{steps()[index]['page']}.py")


def _end() -> None:
    st.session_state.tour_step = None
    st.rerun()


def _closed() -> None:
    """The visitor closed the window (the X, Escape, or a click outside it)."""
    st.session_state.tour_open = False


@st.dialog("Guided tour", width="medium", on_dismiss=_closed)
def _window(index: int) -> None:
    all_steps = steps()
    step, last = all_steps[index], index == len(all_steps) - 1
    st.caption(f"Window {index + 1} of {len(all_steps)}. Synthetic data, fictional company.")
    st.subheader(step["title"])
    for key, label in PARTS.items():
        st.markdown(f"**{label}** {step[key].strip()}")

    back, look, forward = st.columns(3)
    if back.button("Back", disabled=index == 0, width="stretch"):
        _go(index - 1)
    if look.button("Look at the page", width="stretch"):
        _closed()
        st.rerun()
    if forward.button("Finish" if last else "Next", type="primary", width="stretch"):
        if last:
            _end()
        _go(index + 1)


def _bar(index: int) -> None:
    """The tour, folded away: one line at the top of the page while the window is closed."""
    all_steps = steps()
    with st.container(border=True):
        text, reopen, forward, end = st.columns([5, 2, 1, 1])
        text.markdown(
            f"**Guided tour, window {index + 1} of {len(all_steps)}:** {all_steps[index]['title']}"
        )
        if reopen.button("Show the explanation", width="stretch"):
            st.session_state.tour_open = True
            st.rerun()
        if index < len(all_steps) - 1 and forward.button("Next", type="primary", width="stretch"):
            _go(index + 1)
        if end.button("End", width="stretch"):
            _end()
