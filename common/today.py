"""What day is it in the warehouse? Synthetic data, fictional company.

The data runs on a simulated calendar, so "today" is never the real clock: it is the
latest day the gold tables describe.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from common.paths import DATA_DIR
from common.warehouse import open_warehouse


def warehouse_today(data_dir: Path = DATA_DIR) -> date:
    warehouse = open_warehouse(data_dir)
    latest = warehouse.query("SELECT max(snapshot_date) AS today FROM gold.account_current")
    warehouse.close()
    return pd.Timestamp(latest["today"][0]).date()
