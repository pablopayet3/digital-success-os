"""The operational store: what the system is doing right now.

Synthetic data, fictional company.

The warehouse (DuckDB or Databricks) answers questions about the past. This
store holds live state that changes one row at a time: who is enrolled in which
play, which step they are on, which tasks are waiting for a human. In the real
company this is the CS platform. Here it is a small SQL database:

    dev   a SQLite file (data/ops.db)
    prod  Postgres (the DATABASE_URL secret)

The same code runs on both, through SQLAlchemy. Dates are stored as ISO text
(2026-09-28) and JSON as text, so the two databases behave identically.
Every pipeline run copies these tables into the warehouse (bronze.ops_*), which is
how operational data reaches the metrics.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, inspect, text

from common.paths import DATA_DIR
from common.settings import load_settings

# table name -> column definitions
TABLES = {
    # One row per account per play version: the account's place in a journey.
    "enrollments": """
        enrollment_id TEXT PRIMARY KEY,
        account_id TEXT NOT NULL,
        play_id TEXT NOT NULL,
        play_version INTEGER NOT NULL,
        arm TEXT NOT NULL,
        rollout_stage TEXT NOT NULL,
        status TEXT NOT NULL,
        exit_reason TEXT,
        trigger_signal TEXT,
        trigger_evidence TEXT,
        contact_id TEXT,
        current_step TEXT,
        next_action_on TEXT,
        highest_tier TEXT,
        enrolled_on TEXT NOT NULL,
        closed_on TEXT
    """,
    # Why each account entered, was held out, or was kept out of a play.
    "audit_log": """
        run_date TEXT NOT NULL,
        account_id TEXT NOT NULL,
        play_id TEXT NOT NULL,
        decision TEXT NOT NULL,
        reason TEXT
    """,
    # Every touch delivered to a customer (email, in-app prompt, agent conversation).
    "touches": """
        touch_id TEXT PRIMARY KEY,
        touch_date TEXT NOT NULL,
        account_id TEXT NOT NULL,
        contact_id TEXT,
        play_id TEXT NOT NULL,
        enrollment_id TEXT,
        step_id TEXT,
        channel TEXT NOT NULL,
        tier TEXT NOT NULL,
        template TEXT,
        subject TEXT,
        outcome TEXT
    """,
    # What happened inside each journey, step by step.
    "journey_events": """
        event_date TEXT NOT NULL,
        enrollment_id TEXT NOT NULL,
        account_id TEXT NOT NULL,
        play_id TEXT NOT NULL,
        step_id TEXT,
        event TEXT NOT NULL,
        detail TEXT
    """,
    # Tasks for humans. The packet column holds the full handoff packet as JSON.
    "ctas": """
        cta_id TEXT PRIMARY KEY,
        account_id TEXT NOT NULL,
        contact_id TEXT,
        play_id TEXT,
        enrollment_id TEXT,
        step_id TEXT,
        source TEXT NOT NULL,
        queue TEXT NOT NULL,
        priority TEXT NOT NULL,
        reason_code TEXT NOT NULL,
        title TEXT NOT NULL,
        packet TEXT NOT NULL,
        status TEXT NOT NULL,
        created_on TEXT NOT NULL,
        sla_due_on TEXT NOT NULL,
        picked_up_on TEXT,
        resolved_on TEXT,
        outcome TEXT,
        outcome_notes TEXT,
        resolved_by TEXT,
        next_state TEXT
    """,
    # Consent changes the system made itself (for example an "unsubscribe" reply).
    "consent_changes": """
        changed_on TEXT NOT NULL,
        contact_id TEXT NOT NULL,
        account_id TEXT NOT NULL,
        new_status TEXT NOT NULL,
        source TEXT NOT NULL
    """,
    # Accounts whose outbound emails are on hold (no reachable admin, open complaint).
    "paused_accounts": """
        account_id TEXT PRIMARY KEY,
        reason TEXT NOT NULL,
        paused_on TEXT NOT NULL,
        cta_id TEXT
    """,
    # Raised when a queue has more open work than its team can do.
    "queue_alerts": """
        alert_date TEXT NOT NULL,
        queue TEXT NOT NULL,
        open_ctas INTEGER NOT NULL,
        capacity_per_day INTEGER NOT NULL,
        message TEXT NOT NULL
    """,
    # The feedback loop: handoffs a human judged unnecessary, waiting to become eval cases.
    "eval_candidates": """
        cta_id TEXT PRIMARY KEY,
        created_on TEXT NOT NULL,
        source TEXT NOT NULL,
        reason_code TEXT,
        human_notes TEXT,
        packet TEXT NOT NULL
    """,
    # Every conversation an AI agent had: what was said, which tools ran, how it ended.
    "conversations": """
        conversation_id TEXT PRIMARY KEY,
        day TEXT NOT NULL,
        account_id TEXT NOT NULL,
        contact_id TEXT,
        play_id TEXT,
        enrollment_id TEXT,
        scenario TEXT,
        prompt_version TEXT,
        outcome TEXT NOT NULL,
        reason_code TEXT,
        escalated_by TEXT,
        queue TEXT,
        customer_turns INTEGER,
        transcript TEXT NOT NULL,
        tool_calls TEXT,
        searches TEXT,
        llm_calls INTEGER,
        cached_llm_calls INTEGER,
        cost_usd REAL,
        latency_ms INTEGER,
        trace_file TEXT,
        cta_id TEXT,
        feedback TEXT,
        answered_by TEXT
    """,
    # What the mailbox triage agent decided for each reply in the shared mailbox.
    "mailbox_triage": """
        message_id TEXT PRIMARY KEY,
        processed_on TEXT NOT NULL,
        account_id TEXT,
        contact_id TEXT,
        intent TEXT NOT NULL,
        sentiment TEXT,
        confidence REAL,
        action TEXT NOT NULL,
        cta_id TEXT,
        details TEXT
    """,
    # Contacts the system has learned something about that the CRM does not know yet.
    "contact_flags": """
        contact_id TEXT PRIMARY KEY,
        account_id TEXT NOT NULL,
        flag TEXT NOT NULL,
        flagged_on TEXT NOT NULL,
        source TEXT NOT NULL
    """,
    # Sentiment and theme of NPS comments and ticket texts, from the classifier.
    "text_classifications": """
        text_id TEXT PRIMARY KEY,
        kind TEXT NOT NULL,
        account_id TEXT,
        sentiment TEXT NOT NULL,
        theme TEXT,
        confidence REAL,
        classified_on TEXT NOT NULL
    """,
}


class Store:
    def __init__(self, url: str):
        self.engine = create_engine(url)
        with self.engine.begin() as con:
            for name, columns in TABLES.items():
                con.execute(text(f"CREATE TABLE IF NOT EXISTS {name} ({columns})"))
        self._add_new_columns()

    def _add_new_columns(self) -> None:
        """A store made by an older version gains any column added since. Nothing is removed."""
        inspector = inspect(self.engine)
        for name, columns in TABLES.items():
            existing = {column["name"] for column in inspector.get_columns(name)}
            for definition in columns.split(","):
                if definition.split()[0] not in existing:
                    self.execute(f"ALTER TABLE {name} ADD COLUMN {' '.join(definition.split())}")

    def rows(self, sql: str, **params) -> list[dict]:
        """Run a SELECT. Returns a list of rows, each a dictionary."""
        with self.engine.connect() as con:
            return [dict(row._mapping) for row in con.execute(text(sql), params)]

    def one(self, sql: str, **params) -> dict | None:
        found = self.rows(sql, **params)
        return found[0] if found else None

    def execute(self, sql: str, **params) -> None:
        with self.engine.begin() as con:
            con.execute(text(sql), params)

    def insert(self, table: str, *rows: dict) -> None:
        """Add one or more rows to a table."""
        if not rows:
            return
        columns = list(rows[0])
        names = ", ".join(columns)
        values = ", ".join(f":{column}" for column in columns)
        sql = f"INSERT INTO {table} ({names}) VALUES ({values})"
        with self.engine.begin() as con:
            con.execute(text(sql), list(rows))

    def update(self, table: str, key: dict, **values) -> None:
        """Change columns on the rows that match `key`, e.g. key={"cta_id": "CTA-00012"}."""
        assignments = ", ".join(f"{column} = :{column}" for column in values)
        condition = " AND ".join(f"{column} = :key_{column}" for column in key)
        params = {**values, **{f"key_{column}": value for column, value in key.items()}}
        self.execute(f"UPDATE {table} SET {assignments} WHERE {condition}", **params)

    def next_id(self, table: str, prefix: str) -> str:
        """Running ids such as CTA-00001. Fine for one writer at a time."""
        count = self.one(f"SELECT count(*) AS n FROM {table}")["n"]
        return f"{prefix}-{count + 1:05d}"

    def table(self, name: str) -> pd.DataFrame:
        """A whole table as a DataFrame (used to copy it into the warehouse)."""
        frame = pd.DataFrame(self.rows(f"SELECT * FROM {name}"))
        return frame if len(frame) else pd.DataFrame(columns=_column_names(name))


def _column_names(table: str) -> list[str]:
    return [line.split()[0] for line in TABLES[table].strip().splitlines() if line.strip()]


def open_store(data_dir: Path = DATA_DIR) -> Store:
    """Open the operational store of the current environment."""
    settings = load_settings()
    if settings.operational_store.startswith("sqlite"):
        return Store(f"sqlite:///{(data_dir / 'ops.db').as_posix()}")
    return Store(settings.operational_store_url)
