"""The whole data pipeline in one call: landing files to tested gold tables.

Synthetic data, fictional company.

Run with:  uv run python run.py pipeline

Steps:
  1. ingest      validate and load the landing files into bronze (bad rows to dead letter)
  2. dbt stage 1 build silver and the gold facts (usage, setup, health score), with tests
  3. score       apply the churn and expansion models, write scores back to gold
  4. dbt stage 2 build what depends on scores: account_daily (lifecycle), signals
  5. freshness   check that the event data was loaded recently
  6. contract    compare gold.account_daily with contracts/account_daily.yaml

Results of the tests, the freshness check and the contract check are kept in the
warehouse (gold.dq_*) so the app can show them.

The same steps run in both environments. With DSO_ENV=dev the warehouse is a local
DuckDB file; with DSO_ENV=prod it is Databricks (same dbt models, target `prod`).
"""

from __future__ import annotations

from pathlib import Path

from analytics.score import score_accounts
from analytics.train import MODEL_DIR
from common.paths import DATA_DIR
from common.settings import load_settings
from common.warehouse import open_warehouse
from contracts.check import check_contract
from ingest.load import run_ingest
from ingest.transform import run_dbt, save_freshness, save_test_results

SCORED = "tag:scored"  # dbt models that need the model scores


def run_pipeline(
    data_dir: Path = DATA_DIR, verbose: bool = True, model_dir: Path = MODEL_DIR
) -> bool:
    """Run every step. Returns True when all tests and contract checks pass."""
    quiet = [] if verbose else ["--quiet"]
    ingest(data_dir, verbose)

    facts_ok = run_dbt([*quiet, "build", "--exclude", SCORED], data_dir)
    save_test_results(data_dir)
    score_accounts(data_dir, model_dir)
    signals_ok = run_dbt([*quiet, "build", "--select", SCORED], data_dir)
    tests = save_test_results(data_dir, append=True)

    run_dbt([*quiet, "source", "freshness"], data_dir)
    save_freshness(data_dir)
    contract = check_contract(data_dir)
    if verbose:
        print_summary(data_dir, tests, contract)
    return facts_ok and signals_ok and all(check["passed"] for check in contract)


def ingest(data_dir: Path, verbose: bool) -> None:
    """Load the landing files into bronze, in the warehouse of the current environment."""
    if load_settings().warehouse == "databricks":
        from ingest.load_databricks import run_ingest_databricks

        warehouse = open_warehouse(data_dir)
        summary = run_ingest_databricks(warehouse, data_dir)
        warehouse.close()
        if verbose:
            print("Ingest to Databricks finished:", summary)
    else:
        run_ingest(data_dir, verbose=verbose)


def print_summary(data_dir: Path, tests, contract: list[dict]) -> None:
    warehouse = open_warehouse(data_dir)
    print("\nData quality summary")
    quality = warehouse.query(
        "SELECT stage, measure, row_count FROM gold.dq_summary ORDER BY sort_order, measure"
    )
    for row in quality.itertuples():
        print(f"  [{row.stage}] {row.measure}: {int(row.row_count):,}")
    freshness = warehouse.query("SELECT source, status, hours_since_load FROM gold.dq_freshness")
    for row in freshness.itertuples():
        print(f"  [freshness] {row.source}: {row.status} ({row.hours_since_load:.1f}h since load)")

    print("\nSignals firing today in the pilot segment (uncovered accounts)")
    firing = warehouse.query(
        """
        SELECT signals.signal_id, count(*) AS accounts
        FROM gold.signals AS signals
        INNER JOIN gold.account_current AS today
            ON signals.account_id = today.account_id
            AND signals.snapshot_date = today.snapshot_date
        WHERE today.coverage_tier = 'uncovered'
        GROUP BY signals.signal_id
        ORDER BY accounts DESC
        """
    )
    for row in firing.itertuples():
        print(f"  {row.signal_id}: {row.accounts}")
    warehouse.close()

    passed = int((tests["status"] == "pass").sum())
    print(f"\ndbt tests: {passed} of {len(tests)} passed")
    kept = sum(1 for check in contract if check["passed"])
    print(f"data contract (gold.account_daily): {kept} of {len(contract)} checks passed")
    for check in contract:
        if not check["passed"]:
            print(f"  BROKEN: {check['check']} ({check['detail']})")


if __name__ == "__main__":
    run_pipeline()
