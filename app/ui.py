"""Small helpers shared by every page. Synthetic data, fictional company."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pandas as pd
import streamlit as st

from agents.llm import get_llm
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


def refresh() -> None:
    """Forget cached query results (after something changed) and redraw the page."""
    st.cache_data.clear()
    st.rerun()
