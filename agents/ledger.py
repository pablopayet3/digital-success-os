"""What the public demo has spent on the model, kept where a restart cannot reset it.

Synthetic data, fictional company. See ADR 0024.

A normal run counts its spend in memory and stops at its limit (agents/llm.py). The
public demo is different: it runs for days, anyone can type to it, and its host restarts
it whenever it has been idle. A total kept in memory would start again from zero each
time. So this total is kept in the operational store, one row per paid call.

The table is deliberately not one of the store's demo tables (common/store.py TABLES):
an admin's "Reset the demo data" must not hand out a fresh budget.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.exc import SQLAlchemyError

from common.store import Store


class SpendLedger:
    def __init__(self, store: Store):
        self.store = store
        store.execute(
            "CREATE TABLE IF NOT EXISTS llm_spend ("
            "spent_at TEXT NOT NULL, role TEXT NOT NULL, "
            "model TEXT NOT NULL, cost_usd REAL NOT NULL)"
        )

    def spent(self) -> float:
        """US dollars spent so far. If the total cannot be read, nothing more may be spent."""
        try:
            row = self.store.one("SELECT coalesce(sum(cost_usd), 0) AS total FROM llm_spend")
        except SQLAlchemyError:
            return float("inf")
        return float(row["total"])

    def add(self, role: str, model: str, cost_usd: float) -> None:
        """Record one paid call. The time is the real clock: this is real money."""
        now = datetime.now(UTC).isoformat(timespec="seconds")
        self.store.insert(
            "llm_spend", {"spent_at": now, "role": role, "model": model, "cost_usd": cost_usd}
        )
