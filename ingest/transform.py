"""Run dbt from Python and keep its test results in the warehouse.

Synthetic data, fictional company. dbt does the transformation work (bronze to
silver to gold) and runs the data tests. This module starts it against the
warehouse of the current environment (DuckDB in dev, Databricks in prod), then
copies the test results into `gold.dq_test_results`, so the app can show them
next to the other data-quality numbers.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd

from common.config import load_yaml
from common.paths import DATA_DIR, ROOT
from common.settings import load_settings
from common.warehouse import open_warehouse
from ingest.load import warehouse_path

DBT_DIR = ROOT / "dbt"


def dbt_target_dir() -> Path:
    """Where dbt writes its working files. DBT_TARGET_PATH overrides the default.

    (Useful on Windows when the project sits in a very long folder path: dbt's
    file names can then exceed the 260-character limit.)
    """
    return Path(os.environ.get("DBT_TARGET_PATH", DBT_DIR / "target"))


def dbt_variables() -> str:
    """Settings that live in config/ and that the SQL models need (health weights and bands)."""
    health = load_yaml("health.yaml")
    return json.dumps({"health_weights": health["weights"], "health_bands": health["bands"]})


def run_dbt(command: list[str], data_dir: Path = DATA_DIR) -> bool:
    """Run a dbt command, for example ["build"]. Returns True when it succeeded."""
    from dbt.cli.main import dbtRunner  # imported here because it is slow to load

    os.environ["DSO_WAREHOUSE"] = str(warehouse_path(data_dir))
    arguments = [
        *command,
        "--project-dir", str(DBT_DIR),
        "--profiles-dir", str(DBT_DIR),
        "--target", load_settings().dbt_target,
        "--vars", dbt_variables(),
    ]  # fmt: skip
    return dbtRunner().invoke(arguments).success


def save_test_results(data_dir: Path = DATA_DIR, append: bool = False) -> pd.DataFrame:
    """Copy the outcome of the last dbt run's tests into gold.dq_test_results.

    The pipeline runs dbt in two stages; the second stage appends to the first.
    """
    results = json.loads((dbt_target_dir() / "run_results.json").read_text(encoding="utf-8"))
    rows = [
        {
            "test_name": result["unique_id"].split(".")[2],
            "status": result["status"],
            "failures": result.get("failures") or 0,
            "seconds": round(result.get("execution_time", 0.0), 3),
            "run_at": results["metadata"]["generated_at"],
        }
        for result in results["results"]
        if result["unique_id"].startswith("test.")
    ]
    frame = pd.DataFrame(rows)
    warehouse = open_warehouse(data_dir)
    if append:
        earlier = warehouse.query("SELECT * FROM gold.dq_test_results")
        frame = pd.concat([earlier, frame], ignore_index=True)
    warehouse.write_table("gold.dq_test_results", frame)
    warehouse.close()
    return frame


def save_freshness(data_dir: Path = DATA_DIR) -> pd.DataFrame:
    """Copy the outcome of `dbt source freshness` into gold.dq_freshness."""
    results = json.loads((dbt_target_dir() / "sources.json").read_text(encoding="utf-8"))
    rows = [
        {
            "source": result["unique_id"].split(".", 2)[2],
            "status": result["status"],  # pass | warn | error
            "last_loaded_at": result.get("max_loaded_at"),
            "hours_since_load": round(result.get("max_loaded_at_time_ago_in_s", 0.0) / 3600, 2),
            "checked_at": results["metadata"]["generated_at"],
        }
        for result in results["results"]
    ]
    frame = pd.DataFrame(rows)
    warehouse = open_warehouse(data_dir)
    warehouse.write_table("gold.dq_freshness", frame)
    warehouse.close()
    return frame
