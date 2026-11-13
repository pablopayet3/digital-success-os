"""Small helpers shared by every page. Synthetic data, fictional company."""

from __future__ import annotations

import json
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
    """The top of the Overview: what this is, the workflow, and a guide to the pages."""
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
        "**Who uses it.** At a company, this system is internal. Its teams work in it, and "
        "customers see only the messages it sends them. This application shows each part so "
        "that it can be inspected."
    )
    st.markdown(
        "**Three terms used on every page.** A *signal* is a warning sign or an opportunity "
        "found in a customer's data, such as a setup that has stalled. A *play* is the prepared "
        "response to one signal, and a customer is *in a play* while it is receiving that "
        "response. A *holdout* is a group of similar customers deliberately left alone, so "
        "that the effect of a play can be measured."
    )
    terms_in_detail(job)
    st.subheader("The workflow, from signal to outcome")
    st.caption("Each card is one step. The second line names the team responsible for it.")
    workflow(job["workflow"])
    st.subheader("A guide to the pages")
    # A plain table, so that long sentences wrap and nothing is cut off.
    table = ["| Page | What it covers | What you will find |", "|---|---|---|"]
    for page, found in job["pages"].items():
        covers = "; ".join(line["line"] for line in job["lines"] if page in line["pages"])
        table.append(f"| **{PAGE_NAMES[page]}** | {covers} | {found.strip()} |")
    st.markdown("\n".join(table))


def terms_in_detail(job: dict) -> None:
    """Three expanders under the three terms: every signal, one play taken apart, the holdout."""
    from engine.catalog import load_catalog  # imported here: only the Overview needs it

    plays = load_catalog().plays
    with st.expander("See every signal the system looks for"):
        table = ["| Signal | Kind | It fires when |", "|---|---|---|"]
        for signal in job["signals"]:
            table.append(
                f"| **{signal['name']}** | {signal['kind']} | {signal['fires_when'].strip()} |"
            )
        st.markdown("\n".join(table))
    with st.expander("See what a play is made of"):
        play = max(plays, key=lambda play: len(play.intervention_ladder))
        names = {signal["id"]: signal["name"] for signal in job["signals"]}
        starts = ", ".join(names.get(trigger, trigger) for trigger in play.trigger)
        steps = "\n".join(
            f"   - *{str(rung.tier).capitalize()}.* {rung.action} {rung.move_up_when}"
            for rung in play.intervention_ladder
        )
        st.markdown(
            f"Every play has the same five parts. This one is **{play.name}**: "
            f"{play.objective}\n\n"
            f"1. **The signal that starts it.** {starts}.\n"
            "2. **Who may enter.** Customers in the pilot, unless a rule keeps them out: for "
            "example a customer already in this play, or one in the middle of a renewal "
            "negotiation.\n"
            "3. **The steps, in order.** Each step is tried before the next, more costly "
            f"one.\n{steps}\n"
            f"4. **The holdout.** {play.holdout_pct:.0%} of the customers who qualify are "
            "deliberately left alone, for comparison.\n"
            "5. **The measure of success, named before launch.** "
            f"{play.success_metric['description']}"
        )
        st.caption("All the plays are listed on the Plays and experiments page.")
    with st.expander("See how a holdout works"):
        st.markdown(
            "When a customer qualifies for a play, a fixed rule decides whether the customer "
            "enters the play or is held out. The rule works from the customer's identifier, so "
            "nobody chooses, and the same customer always lands on the same side.\n\n"
            "A held-out customer receives nothing from that play. After 30 days the two groups "
            "are compared on the measure named before launch. If the customers in the play did "
            "no better than those left alone, the play did not work, whatever the raw numbers "
            "suggest."
        )
        shares = ", ".join(f"{play.name} {play.holdout_pct:.0%}" for play in plays)
        st.caption(f"Share of qualifying customers held out, by play: {shares}.")


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


def define(label: str) -> str | None:
    """What a number means, in a sentence or two (config/glossary.yaml)."""
    meaning = load_yaml("glossary.yaml").get(label)
    return meaning.strip() if meaning else None


def metric(column, label: str, value, *args, **kwargs) -> None:
    """Show a number with its definition: hovering over its question mark explains it."""
    kwargs.setdefault("help", define(label))
    column.metric(label, value, *args, **kwargs)


def choices_help(label: str) -> str:
    """The hover text of a filter's question mark: what it filters, then one line per choice."""
    block = load_yaml("options.yaml")[label]
    lines = [f"- **{choice}**: {meaning.strip()}" for choice, meaning in block["choices"].items()]
    return block["about"].strip() + "\n\n" + "\n".join(lines)


def choices_table(label: str) -> None:
    """The choices of a filter as a small table: one per line, not one long sentence."""
    block = load_yaml("options.yaml")[label]
    st.caption(block["about"].strip())
    table = [f"| {label} | What it means |", "|---|---|"]
    table += [f"| `{choice}` | {meaning.strip()} |" for choice, meaning in block["choices"].items()]
    st.markdown("\n".join(table))


# The script that shows a choice's meaning when the pointer rests on it.
HINTS = (Path(__file__).parent / "option_hints.html").read_text(encoding="utf-8")


def option_hints() -> None:
    """On every page: resting the pointer on a choice of a filter shows what it means.

    The page library has no hover text for one choice of a list, so a short script adds it
    (app/option_hints.html). The question mark beside the filter carries the same words
    (choices_help), for someone who does not use a pointer.
    """
    hints = {
        choice: meaning.strip()
        for block in load_yaml("options.yaml").values()
        for choice, meaning in block["choices"].items()
    }
    told = json.dumps(hints).replace("</", "<\\/")  # safe inside a script tag
    with st.container(key="option_hints"):
        st.html(HINTS.replace("__HINTS__", told), unsafe_allow_javascript=True)


def job_intro(page: str) -> None:
    """How every page opens: what the page covers, in plain words, and what is on it.

    The words are in config/job.yaml, so the pages, the Overview table and the tour agree.
    """
    job = load_yaml("job.yaml")
    with st.container(border=True):
        for line in job["lines"]:
            if page in line["pages"]:
                st.markdown(f"**{line['line']}.** {line['plain'].strip()}")
        st.markdown(f"**On this page.** {job['pages'][page].strip()}")


def refresh() -> None:
    """Forget cached query results (after something changed) and redraw the page."""
    st.cache_data.clear()
    st.rerun()
