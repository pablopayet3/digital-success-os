"""Exports for other systems. Synthetic data, fictional company.

Two shapes of the same facts:

  crm          one row per account for the CRM: health, scores, lifecycle and the
               signals firing, so a seller sees them on the account page.
  cs_platform  the shape a customer-success platform imports: a company record with an
               overall score and its scorecard measures, and a list of open tasks (CTAs).
               (Which commercial tool this maps to is in the README's tool-mapping table.)
"""

from __future__ import annotations

from pathlib import Path

from common.paths import DATA_DIR
from common.store import open_store
from common.warehouse import open_warehouse
from engine.context import records

ACCOUNT_COLUMNS = """
    account_id, account_name, segment, coverage_tier, edition, arr, renewal_date,
    account_owner, csm, lifecycle_stage, health_score, health_band, health_adoption,
    health_engagement, health_sentiment, health_support, health_commercial,
    churn_risk_score, churn_risk_high, churn_top_reasons, expansion_score,
    expansion_ready, expansion_top_reasons, signals_firing, snapshot_date
"""


def crm_export(data_dir: Path = DATA_DIR) -> list[dict]:
    warehouse = open_warehouse(data_dir)
    rows = records(warehouse.query(f"SELECT {ACCOUNT_COLUMNS} FROM gold.account_current"))
    warehouse.close()
    open_tasks = _open_tasks_by_account(data_dir)
    return [{**row, "open_tasks": len(open_tasks.get(row["account_id"], []))} for row in rows]


def cs_platform_export(data_dir: Path = DATA_DIR) -> dict:
    """Company records with scorecard measures, and open tasks, in an import-ready shape."""
    warehouse = open_warehouse(data_dir)
    rows = records(warehouse.query(f"SELECT {ACCOUNT_COLUMNS} FROM gold.account_current"))
    warehouse.close()
    companies = [
        {
            "Company ID": row["account_id"],
            "Company Name": row["account_name"],
            "Segment": row["segment"],
            "Coverage Tier": row["coverage_tier"],
            "Lifecycle Stage": row["lifecycle_stage"],
            "ARR": row["arr"],
            "Renewal Date": (row["renewal_date"] or "")[:10],
            "CSM": row["csm"],
            "Overall Score": row["health_score"],
            "Overall Score Band": row["health_band"],
            "Scorecard Measures": {
                "Adoption": row["health_adoption"],
                "Engagement": row["health_engagement"],
                "Sentiment": row["health_sentiment"],
                "Support": row["health_support"],
                "Commercial": row["health_commercial"],
            },
            "Churn Risk": row["churn_risk_score"],
            "Expansion Likelihood": row["expansion_score"],
            "As Of": (row["snapshot_date"] or "")[:10],
        }
        for row in rows
    ]
    tasks = [
        {
            "CTA ID": task["cta_id"],
            "Company ID": task["account_id"],
            "Name": task["title"],
            "Type": "Expansion" if task["queue"] == "sales" else "Risk",
            "Reason": task["reason_code"],
            "Priority": task["priority"],
            "Status": task["status"],
            "Owner Queue": task["queue"],
            "Due Date": task["sla_due_on"],
            "Source": task["source"],
            "Playbook": task["play_id"],
        }
        for tasks_of_account in _open_tasks_by_account(data_dir).values()
        for task in tasks_of_account
    ]
    return {"companies": companies, "ctas": tasks}


def _open_tasks_by_account(data_dir: Path) -> dict[str, list[dict]]:
    by_account: dict[str, list[dict]] = {}
    for task in open_store(data_dir).rows("SELECT * FROM ctas WHERE status <> 'resolved'"):
        by_account.setdefault(task["account_id"], []).append(task)
    return by_account
