"""The app: one place to see the whole system. Synthetic data, fictional company.

Run with:  uv run python run.py app      (opens http://localhost:8501)

Each page is a file in app/views/. This file only sets up the navigation and puts
the "synthetic data" banner on every page.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # so pages can import the project

import streamlit as st  # noqa: E402

from app import ui  # noqa: E402

st.set_page_config(page_title="Digital Success OS (synthetic data)", layout="wide")

PAGES = {
    "The system": [
        st.Page("views/overview.py", title="Overview", default=True),
        st.Page("views/accounts.py", title="Accounts"),
        st.Page("views/plays.py", title="Plays and experiments"),
        st.Page("views/agent.py", title="Agents"),
        st.Page("views/console.py", title="Human console"),
    ],
    "Behind it": [
        st.Page("views/quality.py", title="Data quality"),
        st.Page("views/pilot.py", title="Pilot"),
        st.Page("views/operating.py", title="Operating model"),
        st.Page("views/demo.py", title="Live demo"),
    ],
}

page = st.navigation(PAGES)
ui.banner()
if ui.data_is_ready():
    page.run()
else:
    st.title("Digital Success OS")
    st.info(
        "There is no data yet. Build it with `uv run python run.py demo` "
        "(about 15 minutes), then reload this page."
    )
