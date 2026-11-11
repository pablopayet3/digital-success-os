"""Compare the live production table with its data contract.

Synthetic data, fictional company.

The contract (contracts/account_daily.yaml) says what the table promises:
its columns and types, which columns may be empty, its quality rules and how
fresh it must be. This module checks each promise and returns one result per
check. The pipeline stores the results; a test fails if any promise is broken.

It works the same on DuckDB (dev) and Databricks (prod).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import yaml

from common.paths import DATA_DIR, ROOT
from common.warehouse import open_warehouse

CONTRACT_PATH = ROOT / "contracts" / "account_daily.yaml"

# The contract uses five plain type names. Each covers several database types
# (the first names are DuckDB's, the later ones Databricks').
TYPE_FAMILIES = {
    "text": {"VARCHAR", "STRING"},
    "integer": {"TINYINT", "SMALLINT", "INTEGER", "INT", "BIGINT", "LONG", "HUGEINT"},
    "number": {"DOUBLE", "FLOAT", "DECIMAL"},
    "boolean": {"BOOLEAN"},
    "date": {"DATE"},
}


def load_contract(path: Path = CONTRACT_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def check_contract(
    data_dir: Path = DATA_DIR, contract: dict | None = None, save: bool = True
) -> list[dict]:
    """Run every check. Returns a list of {check, passed, detail}.

    With save=True the results are also stored in gold.dq_contract_checks for the app.
    """
    contract = contract or load_contract()
    table = contract["table"]
    schema_name, table_name = table.split(".")
    warehouse = open_warehouse(data_dir)
    results: list[dict] = []

    def record(check: str, passed: bool, detail: str = "") -> None:
        results.append({"check": check, "passed": bool(passed), "detail": detail})

    # 1. The table has exactly the columns the contract lists, with the promised types.
    described = warehouse.query(
        f"""
        SELECT column_name, data_type FROM information_schema.columns
        WHERE table_schema = '{schema_name}' AND table_name = '{table_name}'
        """
    )
    live = {
        name: kind.upper().split("(")[0]
        for name, kind in zip(described["column_name"], described["data_type"], strict=True)
    }
    promised = {column["name"]: column for column in contract["columns"]}
    missing = sorted(set(promised) - set(live))
    undocumented = sorted(set(live) - set(promised))
    record("columns: none missing", not missing, ", ".join(missing))
    record("columns: none undocumented", not undocumented, ", ".join(undocumented))
    wrong_type = [
        f"{name} is {live[name]}, contract says {column['type']}"
        for name, column in promised.items()
        if name in live and live[name] not in TYPE_FAMILIES[column["type"]]
    ]
    record("columns: types match", not wrong_type, "; ".join(wrong_type))

    # 2. Columns that must always have a value really do.
    required = [
        name for name, column in promised.items() if not column["nullable"] and name in live
    ]
    if required:
        gaps = warehouse.query(
            f"SELECT {', '.join(f'count(*) - count({n}) AS {n}' for n in required)} FROM {table}"
        ).iloc[0]
        with_gaps = [f"{name} ({int(gaps[name])} empty)" for name in required if gaps[name]]
        record("columns: required values present", not with_gaps, ", ".join(with_gaps))

    # 3. Every quality rule returns zero rows.
    for rule in contract["quality_rules"]:
        broken = warehouse.query(f"SELECT count(*) AS n FROM ({rule['sql']}) AS broken")
        violations = int(broken["n"][0])
        record(f"rule: {rule['name']}", violations == 0, f"{violations} rows break the rule")

    # 4. The source data is fresh enough.
    freshness = contract["freshness"]
    loaded_at = warehouse.query("SELECT max(_ingested_at) AS loaded_at FROM bronze.events")
    hours = hours_since(loaded_at["loaded_at"][0])
    record(
        f"freshness: {freshness['source']} loaded within {freshness['max_hours_since_load']}h",
        hours is not None and hours <= freshness["max_hours_since_load"],
        f"last load {hours:.1f} hours ago" if hours is not None else "never loaded",
    )

    if save:
        warehouse.write_table("gold.dq_contract_checks", pd.DataFrame(results))
    warehouse.close()
    return results


def hours_since(moment) -> float | None:
    """Hours between a load time (stored in UTC) and now."""
    if moment is None or pd.isna(moment):
        return None
    moment = pd.Timestamp(moment)
    if moment.tzinfo is not None:
        moment = moment.tz_convert("UTC").tz_localize(None)
    now = datetime.now(UTC).replace(tzinfo=None)
    return (now - moment.to_pydatetime()).total_seconds() / 3600
