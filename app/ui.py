"""Small helpers shared by every page. Synthetic data, fictional company."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pandas as pd
import streamlit as st

from agents.llm import get_llm
from common.config import load_yaml
from common.paths import DATA_DIR
from common.store import Store, open_store
from common.warehouse import open_warehouse
from ingest.load import warehouse_path

BAND_COLOURS = {"green": "#2e9e6b", "yellow": "#d9a400", "red": "#cc4b37"}


def data_dir() -> Path:
    return Path(os.environ.get("DSO_DATA_DIR", DATA_DIR))


def data_is_ready() -> bool:
    return warehouse_path(data_dir()).exists()


def banner() -> None:
    """On every page: this is made-up data, and who is playing the model."""
    st.caption(
        ":orange[**Synthetic data, fictional company.**] Lumen Labs and Relay do not exist. "
        f"New AI answers are produced by: **{get_llm().mode}**. "
        "Stored conversations say who answered them."
    )


@st.cache_data(ttl=20, show_spinner=False)
def query(sql: str) -> pd.DataFrame:
    """Run a SELECT on the warehouse. Retries briefly if the pipeline is writing."""
    for attempt in range(5):
        try:
            warehouse = open_warehouse(data_dir())
            try:
                return warehouse.query(sql)
            finally:
                warehouse.close()
        except Exception:
            if attempt == 4:
                raise
            time.sleep(0.6)
    return pd.DataFrame()


def store() -> Store:
    """The operational store (live state: enrolments, tasks, conversations)."""
    return open_store(data_dir())


def rows(sql: str, **parameters) -> pd.DataFrame:
    return pd.DataFrame(store().rows(sql, **parameters))


def today() -> str:
    latest = query("SELECT max(snapshot_date) AS today FROM gold.account_current")
    return str(pd.Timestamp(latest["today"][0]).date())


def pct(value, digits: int = 0) -> str:
    return "n/a" if value is None or pd.isna(value) else f"{value:.{digits}%}"


# The name of each page, as the menu, the tour and the Overview table show it.
PAGE_NAMES = {
    "overview": "Overview",
    "quality": "Data quality",
    "accounts": "Accounts",
    "plays": "Plays and experiments",
    "demo": "Live demo",
    "agent": "Agents",
    "console": "Human console",
    "pilot": "Pilot",
    "operating": "Operating model",
}


def what_this_is() -> None:
    """The top of the Overview: what this is, the workflow, and the role line by line."""
    job = load_yaml("job.yaml")
    st.markdown(
        "**What this is.** A working model of a digital customer-success operation, built on "
        "fictional data. A software company has thousands of customers with no assigned success "
        "manager. This system looks after them. It reads their data every day, finds the "
        "customers who need help, and sends that help automatically: an email first, then an AI "
        "agent, and a person only when one is needed. It then measures whether the help changed "
        "the outcome."
    )
    st.markdown(
        "**Who uses it.** In a company this system is internal. Its teams work in it, and "
        "customers see only what it sends them. This application exists so that each part can "
        "be inspected."
    )
    st.markdown(
        "**Three terms used on every page.** A *signal* is a warning sign or an opportunity "
        "found in a customer's data, such as a setup that has stalled. A *play* is the prepared "
        "response to one signal. A *holdout* is a group of similar customers deliberately left "
        "alone, so that the effect of a play can be measured."
    )
    st.subheader("The workflow, from signal to outcome")
    st.caption("Each card is one step. The second line names the team accountable for it.")
    workflow(job["workflow"])
    st.subheader("The role, line by line")
    # A plain table, so that long sentences wrap and nothing is cut off.
    table = ["| The role asks for | In plain words | Where to look |", "|---|---|---|"]
    for line in job["lines"]:
        pages = ", ".join(PAGE_NAMES[page] for page in line["pages"])
        table.append(f"| **{line['line']}** | {line['plain'].strip()} | {pages} |")
    st.markdown("\n".join(table))


def workflow(stages: list[dict]) -> None:
    """The workflow as a row of cards with arrows between them. Each card names its team."""
    widths = []
    for index, stage in enumerate(stages):
        widths += ([1] if index else []) + [5 if "rungs" in stage else 4]
    slots = iter(st.columns(widths, vertical_alignment="center"))
    for index, stage in enumerate(stages):
        if index:
            next(slots).markdown("**→**")
        with next(slots):
            if "rungs" in stage:
                st.caption(stage["ladder"])
            for card in stage.get("rungs", [stage]):
                with st.container(border=True):
                    st.markdown(f"**{card['step']}**")
                    st.caption(f"Team: {card['team']}" if "team" in card else card["note"])


def job_intro(page: str) -> None:
    """How every page opens: the line of the role it answers, in plain words, and what is here.

    The words are in config/job.yaml, so the pages, the Overview table and the tour agree.
    """
    job = load_yaml("job.yaml")
    with st.container(border=True):
        for line in job["lines"]:
            if page in line["pages"]:
                st.markdown(f"**The role asks for: {line['line']}.** {line['asks'].strip()}")
                st.markdown(f"**In plain words.** {line['plain'].strip()}")
        st.markdown(f"**On this page.** {job['pages'][page].strip()}")


def refresh() -> None:
    """Forget cached query results (after something changed) and redraw the page."""
    st.cache_data.clear()
    st.rerun()
