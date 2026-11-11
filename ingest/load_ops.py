"""Copy the operational store into the warehouse.

Synthetic data, fictional company. The engine keeps its live state (enrolments,
touches, CTAs, outcomes) in a small transactional database. The metrics are
computed in the warehouse. So on every pipeline run the operational tables are
copied, as they are, into bronze (`bronze.ops_enrollments`, `bronze.ops_ctas`,
and so on). In the real company this is the daily load from the CS platform
into the lakehouse.
"""

from __future__ import annotations

from pathlib import Path

from common.paths import DATA_DIR
from common.store import TABLES, open_store
from common.warehouse import open_warehouse


def sync_operational_store(data_dir: Path = DATA_DIR) -> dict[str, int]:
    """Replace every bronze.ops_* table with the current operational table. Returns row counts."""
    store, warehouse = open_store(data_dir), open_warehouse(data_dir)
    counts = {}
    for name in TABLES:
        frame = store.table(name).astype("string")  # loaded as text; typed later, in dbt
        warehouse.write_table(f"bronze.ops_{name}", frame)
        counts[name] = len(frame)
    warehouse.close()
    return counts
