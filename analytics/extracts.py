"""Extracts for a BI tool: the tables a dashboard needs, as CSV files.

Synthetic data, fictional company.

Run with:  uv run python run.py extracts     (writes exports/bi/)

In a company the BI tool reads the gold tables directly. A free, public BI tool
cannot reach a local warehouse, so this writes the same tables as files. Each
file is one gold table, or one aggregate of it, with no logic added: the
definitions stay in dbt, where they are tested. The build guide is
docs/bi-dashboard-guide.md.
"""

from __future__ import annotations

from pathlib import Path

from common.paths import DATA_DIR, ROOT
from common.warehouse import open_warehouse

EXTRACT_DIR = ROOT / "exports" / "bi"

# file name -> the query that fills it
EXTRACTS = {
    # One row per account, as it stands today.
    "accounts.csv": """
        SELECT account_id, account_name, segment, coverage_tier, edition, lifecycle_stage,
               value_tier, arr, seats_licensed, seats_assigned, seat_utilisation, mau_30d,
               prerequisite_closure_pct, health_score, health_band, health_adoption,
               health_engagement, health_sentiment, health_support, health_commercial,
               churn_risk_score, churn_risk_high, expansion_score, expansion_ready,
               days_to_renewal, signals_firing, snapshot_date
        FROM gold.account_current
    """,
    # The trend: one row per day, coverage tier, health band and lifecycle stage.
    "health_daily.csv": """
        SELECT snapshot_date, coverage_tier, health_band, lifecycle_stage,
               count(*) AS accounts, sum(arr) AS arr, sum(mau_30d) AS monthly_active_users,
               avg(health_score) AS avg_health_score,
               avg(prerequisite_closure_pct) AS avg_setup_closure
        FROM gold.account_daily
        GROUP BY snapshot_date, coverage_tier, health_band, lifecycle_stage
    """,
    # One row per account and signal firing today, with its evidence.
    "signals_today.csv": """
        SELECT signals.account_id, accounts.coverage_tier, signals.signal_id, signals.evidence
        FROM gold.signals AS signals
        JOIN gold.account_current AS accounts ON signals.account_id = accounts.account_id
        WHERE signals.snapshot_date = accounts.snapshot_date
    """,
    # One row per enrolment (treatment and holdout) with its outcomes.
    "play_outcomes.csv": "SELECT * FROM gold.metrics_play_outcomes",
    # One row per play: rates, lift, interval, verdict. From `run.py experiments`.
    "play_results.csv": "SELECT * FROM gold.experiment_results",
    # One row per task handed to a person.
    "handoffs.csv": "SELECT * FROM silver.stg_ops_ctas",
    # One row per agent conversation.
    "agent_conversations.csv": "SELECT * FROM silver.stg_ops_conversations",
    # What the pipeline caught.
    "data_quality.csv": "SELECT * FROM gold.dq_summary ORDER BY sort_order",
}


def write_extracts(data_dir: Path = DATA_DIR, folder: Path = EXTRACT_DIR) -> dict[str, int]:
    """Write every extract. Returns the number of rows in each file."""
    folder.mkdir(parents=True, exist_ok=True)
    warehouse = open_warehouse(data_dir)
    counts = {}
    for name, sql in EXTRACTS.items():
        frame = warehouse.query(sql)
        frame.to_csv(folder / name, index=False, lineterminator="\n")
        counts[name] = len(frame)
    warehouse.close()
    return counts
