"""Compare the live production table with its data contract.

Synthetic data, fictional company.

The contract (contracts/account_daily.yaml) says what the table promises:
its columns and types, which columns may be empty, its quality rules and how
fresh it must be. This module checks each promise and returns one result per
check. The pipeline stores the results; a test fails if any promise is broken.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd
import yaml

from common.paths import DATA_DIR, ROOT
from ingest.load import warehouse_path

CONTRACT_PATH = ROOT / "contracts" / "account_daily.yaml"

# The contract uses five plain type names. Each covers several database types.
TYPE_FAMILIES = {
    "text": {"VARCHAR"},
    "integer": {"TINYINT", "SMALLINT", "INTEGER", "BIGINT", "HUGEINT"},
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
    con = duckdb.connect(str(warehouse_path(data_dir)))
    results: list[dict] = []

    def record(check: str, passed: bool, detail: str = "") -> None:
        results.append({"check": check, "passed": bool(passed), "detail": detail})

    # 1. The table has exactly the columns the contract lists, with the promised types.
    described = con.execute(f"DESCRIBE {table}").fetchall()
    live = {name: kind.split("(")[0] for name, kind, *_ in described}
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
        counts = con.execute(
            f"SELECT {', '.join(f'count(*) - count({name})' for name in required)} FROM {table}"
        ).fetchone()
        with_gaps = [f"{name} ({n} empty)" for name, n in zip(required, counts, strict=True) if n]
        record("columns: required values present", not with_gaps, ", ".join(with_gaps))

    # 3. Every quality rule returns zero rows.
    for rule in contract["quality_rules"]:
        violations = con.execute(f"SELECT count(*) FROM ({rule['sql']})").fetchone()[0]
        record(f"rule: {rule['name']}", violations == 0, f"{violations} rows break the rule")

    # 4. The source data is fresh enough.
    freshness = contract["freshness"]
    hours = con.execute(
        "SELECT date_diff('minute', max(_ingested_at), now()::TIMESTAMP) / 60.0 FROM bronze.events"
    ).fetchone()[0]
    record(
        f"freshness: {freshness['source']} loaded within {freshness['max_hours_since_load']}h",
        hours is not None and hours <= freshness["max_hours_since_load"],
        f"last load {hours:.1f} hours ago" if hours is not None else "never loaded",
    )

    if save:
        frame = pd.DataFrame(results)  # noqa: F841 (read by DuckDB below)
        con.execute("CREATE OR REPLACE TABLE gold.dq_contract_checks AS SELECT * FROM frame")
    con.close()
    return results
