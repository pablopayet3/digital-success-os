"""The whole data pipeline in one call: landing files to tested gold tables.

Synthetic data, fictional company.

Run with:  uv run python run.py pipeline

Steps:
  1. ingest     validate and load the landing files into bronze (bad rows to dead letter)
  2. dbt build  build silver and gold, and run every data test
  3. freshness  check that the event data was loaded recently
  4. contract   compare gold.account_daily with contracts/account_daily.yaml
  5. record     keep the test, freshness and contract results in the warehouse for the app
"""

from __future__ import annotations

from pathlib import Path

import duckdb

from common.paths import DATA_DIR
from contracts.check import check_contract
from ingest.load import run_ingest, warehouse_path
from ingest.transform import run_dbt, save_freshness, save_test_results


def run_pipeline(data_dir: Path = DATA_DIR, verbose: bool = True) -> bool:
    """Run ingest, then dbt build (models and tests). Returns True when all tests pass."""
    quiet = [] if verbose else ["--quiet"]
    run_ingest(data_dir, verbose=verbose)
    succeeded = run_dbt([*quiet, "build"], data_dir)
    tests = save_test_results(data_dir)
    run_dbt([*quiet, "source", "freshness"], data_dir)
    save_freshness(data_dir)
    contract = check_contract(data_dir)
    if verbose:
        print_summary(data_dir, tests, contract)
    return succeeded and all(check["passed"] for check in contract)


def print_summary(data_dir: Path, tests, contract: list[dict]) -> None:
    con = duckdb.connect(str(warehouse_path(data_dir)))
    print("\nData quality summary")
    for stage, measure, row_count in con.execute(
        "SELECT stage, measure, row_count FROM gold.dq_summary ORDER BY sort_order, measure"
    ).fetchall():
        print(f"  [{stage}] {measure}: {row_count:,}")
    for source, status, hours in con.execute(
        "SELECT source, status, round(hours_since_load, 1) FROM gold.dq_freshness"
    ).fetchall():
        print(f"  [freshness] {source}: {status} (loaded {hours} hours ago)")
    con.close()
    passed = int((tests["status"] == "pass").sum())
    print(f"\ndbt tests: {passed} of {len(tests)} passed")
    kept = sum(1 for check in contract if check["passed"])
    print(f"data contract (gold.account_daily): {kept} of {len(contract)} checks passed")
    for check in contract:
        if not check["passed"]:
            print(f"  BROKEN: {check['check']} ({check['detail']})")


if __name__ == "__main__":
    run_pipeline()
