"""The guided tour: a slim strip at the top of the page that walks a visitor through the app.

Synthetic data, fictional company. The strip never covers the page. Each stop is one page:
the strip names the page, says which platform and which team do this at a real company
(config/tour.yaml), and offers Back, Next and End. What the page is for is said by the page
itself, in its opening (app/ui.py::job_intro), so the tour has nothing to repeat.

On the hosted demo the tour starts by itself. Locally it starts from the button in the
sidebar, so a live demo is never interrupted.

Where the tour is: `tour_step` in the session is the stop's number, or None when no tour
is running.
"""

from __future__ import annotations

import os

import streamlit as st

from app import ui
from common.config import load_yaml


def stops() -> list[dict]:
    return load_yaml("tour.yaml")["stops"]


def show(current_page: str) -> None:
    """Draw the sidebar button, and the strip when a tour is running."""
    state = st.session_state
    if "tour_step" not in state:
        # A visitor of the hosted demo is greeted by the first stop. Locally, nothing opens.
        state.tour_step = 0 if os.environ.get("DSO_HOSTED") else None
    if st.sidebar.button("Guided tour", width="stretch"):
        _go(0)
    if state.tour_step is None:
        return
    # The visitor may have used the menu: the strip then follows them to the page they chose.
    names = [ui.PAGE_NAMES[stop["page"]] for stop in stops()]
    if names[state.tour_step] != current_page and current_page in names:
        state.tour_step = names.index(current_page)
    _strip(state.tour_step)


def _go(index: int) -> None:
    """Move to a stop and to the page it explains."""
    st.session_state.tour_step = index
    st.switch_page(f"views/{stops()[index]['page']}.py")


def _end() -> None:
    st.session_state.tour_step = None
    st.rerun()


def _strip(index: int) -> None:
    all_stops = stops()
    stop, last = all_stops[index], index == len(all_stops) - 1
    with st.container(border=True):
        text, back, forward, end = st.columns([7, 1, 1, 1], vertical_alignment="center")
        text.markdown(
            f"**Guided tour, stop {index + 1} of {len(all_stops)}: "
            f"{ui.PAGE_NAMES[stop['page']]}.** {stop['company'].strip()}"
        )
        if back.button("Back", disabled=index == 0, width="stretch"):
            _go(index - 1)
        if forward.button("Finish" if last else "Next", type="primary", width="stretch"):
            if last:
                _end()
            _go(index + 1)
        if end.button("End", width="stretch"):
            _end()
