"""The app: one place to see the whole system. Synthetic data, fictional company.

Run with:  uv run python run.py app      (opens http://localhost:8501)

Each page is a file in app/views/. This file only sets up the navigation, puts the
"synthetic data" banner on every page, and shows the guided tour (app/tour.py).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # so pages can import the project

import streamlit as st  # noqa: E402

from app import tour, ui  # noqa: E402

st.set_page_config(page_title="Digital Success OS (synthetic data)", layout="wide")

# The menu follows the order of the work: data, then models, then the responses, then
# how it is run. The names are in app/ui.py, so the tour and the pages use the same ones.
MENU = {
    "Start here": ["overview"],
    "1. Data and models": ["quality", "accounts"],
    "2. Journeys, AI agent, handoffs": ["plays", "demo", "agent", "console"],
    "3. Pilot, ownership, decisions": ["pilot", "operating"],
}
PAGES = {
    section: [
        st.Page(f"views/{name}.py", title=ui.PAGE_NAMES[name], default=name == "overview")
        for name in names
    ]
    for section, names in MENU.items()
}

page = st.navigation(PAGES)
ui.banner()
ui.option_hints()  # the meaning of each choice in a filter, when the pointer rests on it
if ui.data_is_ready():
    tour.show(page.title)  # the guided tour's strip, when a tour is running
    page.run()
else:
    st.title("Digital Success OS")
    st.info(
        "There is no data yet. Build it with `uv run python run.py demo` "
        "(about 15 minutes), then reload this page."
    )
