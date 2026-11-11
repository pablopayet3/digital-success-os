"""Everything the engine knows on a given day, loaded once.

Synthetic data, fictional company. The engine reads the warehouse's gold tables
(what is true about each account today) and the operational store (what we have
already done). It never reads raw data, and never the simulator's ground truth.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from common.config import load_yaml
from common.paths import DATA_DIR
from common.store import Store, open_store
from common.warehouse import open_warehouse
from engine.catalog import Catalog, load_catalog


@dataclass
class DayContext:
    today: date
    data_dir: Path
    store: Store
    catalog: Catalog
    segments: list[str]  # coverage tiers the plays may run on (config/rollout.yaml)
    accounts: dict[str, dict]  # gold.account_current, by account id
    signals: dict[str, dict[str, str]]  # account id -> {signal id: evidence}
    contacts: dict[str, list[dict]]  # account id -> contacts (gold.dim_contact)
    opted_out: set[str] = field(default_factory=set)  # contacts who opted out since the CRM sync
    paused: set[str] = field(default_factory=set)  # accounts whose emails are on hold

    @property
    def day(self) -> str:
        """Today as text, the way dates are stored in the operational store."""
        return self.today.isoformat()

    def days_ago(self, days: int) -> str:
        return (self.today - timedelta(days=days)).isoformat()

    def days_ahead(self, days: int) -> str:
        return (self.today + timedelta(days=days)).isoformat()


def records(frame: pd.DataFrame) -> list[dict]:
    """A DataFrame as a list of plain dictionaries (no numpy or pandas types inside)."""
    return json.loads(frame.to_json(orient="records", date_format="iso"))


def load_day(
    data_dir: Path = DATA_DIR, store: Store | None = None, catalog: Catalog | None = None
) -> DayContext:
    """Read today's accounts, signals and contacts, plus the engine's own state."""
    store = store or open_store(data_dir)
    warehouse = open_warehouse(data_dir)
    accounts = warehouse.query("SELECT * FROM gold.account_current")
    today = pd.Timestamp(accounts["snapshot_date"].max()).date()
    signals = warehouse.query(
        """
        SELECT signals.account_id, signals.signal_id, signals.evidence
        FROM gold.signals AS signals
        WHERE signals.snapshot_date = (SELECT max(snapshot_date) FROM gold.account_current)
        """
    )
    contacts = warehouse.query(
        """
        SELECT account_id, contact_id, full_name, email, persona, role, consent_status,
               email_valid, can_email, is_valid_admin
        FROM gold.dim_contact
        """
    )
    warehouse.close()

    signals_by_account: dict[str, dict[str, str]] = {}
    for row in records(signals):
        signals_by_account.setdefault(row["account_id"], {})[row["signal_id"]] = row["evidence"]
    contacts_by_account: dict[str, list[dict]] = {}
    for row in records(contacts):
        contacts_by_account.setdefault(row["account_id"], []).append(row)

    opt_outs = store.rows("SELECT contact_id FROM consent_changes WHERE new_status = 'opted_out'")
    return DayContext(
        today=today,
        data_dir=data_dir,
        store=store,
        catalog=catalog or load_catalog(),
        segments=load_yaml("rollout.yaml")["segments"],
        accounts={row["account_id"]: row for row in records(accounts)},
        signals=signals_by_account,
        contacts=contacts_by_account,
        opted_out={row["contact_id"] for row in opt_outs},
        paused={row["account_id"] for row in store.rows("SELECT account_id FROM paused_accounts")},
    )
