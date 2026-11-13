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


class VoiceLedger:
    """What the public demo's voice sessions have cost, kept in the store (ADR 0028).

    The voice service bills by the minute of conversation, and its bill is not visible to
    this system. So each new session reserves its longest possible cost before it starts.
    When the session ends, the page reports how long it lasted, and the reservation shrinks
    to that length. A session whose end is never reported keeps its full reservation, so
    the total can be over-counted but never under-counted. Like llm_spend, this table is
    not reset by the admin's "Reset the demo data".
    """

    def __init__(self, store: Store):
        self.store = store
        store.execute(
            "CREATE TABLE IF NOT EXISTS voice_spend ("
            "session_id TEXT PRIMARY KEY, started_at TEXT NOT NULL, "
            "reserved_usd REAL NOT NULL, final_usd REAL)"
        )

    def spent(self) -> float:
        """US dollars counted so far. If the total cannot be read, nothing more may be spent."""
        try:
            row = self.store.one(
                "SELECT coalesce(sum(coalesce(final_usd, reserved_usd)), 0) AS total "
                "FROM voice_spend"
            )
        except SQLAlchemyError:
            return float("inf")
        return float(row["total"])

    def reserve(self, session_id: str, reserved_usd: float) -> None:
        """Count a new session at its longest possible cost, before it starts."""
        now = datetime.now(UTC).isoformat(timespec="seconds")
        self.store.insert(
            "voice_spend",
            {"session_id": session_id, "started_at": now, "reserved_usd": reserved_usd},
        )

    def finish(self, session_id: str, final_usd: float) -> bool:
        """Shrink a reservation to the session's real cost. It can never grow, and a
        session can be finished only once."""
        row = self.store.one(
            "SELECT reserved_usd, final_usd FROM voice_spend WHERE session_id = :id",
            id=session_id,
        )
        if row is None or row["final_usd"] is not None:
            return False
        final = min(float(row["reserved_usd"]), max(float(final_usd), 0.0))
        self.store.update("voice_spend", {"session_id": session_id}, final_usd=final)
        return True
