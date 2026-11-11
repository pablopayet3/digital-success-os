"""Load the landing files into the bronze layer of the warehouse.

Synthetic data, fictional company.

Two kinds of source, two loading patterns:

- Product events are an append-only stream. Each daily file is validated line by
  line and loaded once. A load log remembers which files are in, so running the
  loader again does nothing (it is idempotent). Bad lines go to the dead-letter
  queue with the reason.
- CRM, licence, support, NPS, email and mailbox files are snapshots: the full
  current state. They are loaded as-is (all text) and replaced on every run.
  Cleaning and typing happen later, in dbt, where they can be tested.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pandas as pd

from common.paths import DATA_DIR
from ingest.schemas import validate_event

SNAPSHOT_FILES = {
    "crm_accounts": "crm_accounts.csv",
    "crm_contacts": "crm_contacts.csv",
    "crm_opportunities": "crm_opportunities.csv",
    "licenses": "licenses.csv",
    "tickets": "tickets.csv",
    "nps": "nps.csv",
    "email_engagement": "email_engagement.csv",
}

SETUP_SQL = """
CREATE SCHEMA IF NOT EXISTS bronze;
CREATE TABLE IF NOT EXISTS bronze.events (
    event_id VARCHAR, occurred_at TIMESTAMP, account_id VARCHAR, user_id VARCHAR,
    event_name VARCHAR, properties JSON, _ingested_at TIMESTAMP, _source_file VARCHAR
);
CREATE TABLE IF NOT EXISTS bronze.dead_letter (
    source VARCHAR, source_file VARCHAR, line_number INTEGER, reason VARCHAR,
    detail VARCHAR, raw VARCHAR, _ingested_at TIMESTAMP
);
CREATE TABLE IF NOT EXISTS bronze._load_log (
    source_file VARCHAR, loaded_at TIMESTAMP, rows_loaded INTEGER, rows_rejected INTEGER
);
"""


def warehouse_path(data_dir: Path = DATA_DIR) -> Path:
    return data_dir / "warehouse.duckdb"


def run_ingest(data_dir: Path = DATA_DIR, verbose: bool = True) -> dict:
    """Load everything new from data/landing/ into bronze. Returns what it did."""
    landing = data_dir / "landing"
    con = duckdb.connect(str(warehouse_path(data_dir)))
    con.execute(SETUP_SQL)

    load_log = con.execute("SELECT source_file FROM bronze._load_log").fetchall()
    already_loaded = {row[0] for row in load_log}
    summary = {"event_files_loaded": 0, "events_loaded": 0, "events_rejected": 0}
    for path in sorted((landing / "events").glob("*.jsonl")):
        if path.name in already_loaded:
            continue
        loaded, rejected = load_event_file(con, path, data_dir)
        summary["event_files_loaded"] += 1
        summary["events_loaded"] += loaded
        summary["events_rejected"] += rejected

    for table, file_name in SNAPSHOT_FILES.items():
        summary[table] = load_snapshot(con, table, landing / file_name)
    summary["mailbox"] = load_mailbox(con, landing / "mailbox")
    con.close()

    if verbose:
        print("Ingest finished:")
        for name, value in summary.items():
            print(f"  {name}: {value:,}")
    return summary


def load_event_file(con: duckdb.DuckDBPyConnection, path: Path, data_dir: Path) -> tuple[int, int]:
    """Validate one file of events. Good rows go to bronze.events, bad rows to dead letter."""
    now = datetime.now(UTC).replace(tzinfo=None)
    good, bad = [], []
    with open(path, encoding="utf-8") as f:
        for line_number, line in enumerate(f, start=1):
            line = line.rstrip("\n")
            event, reason, detail = validate_event(line)
            if event is None:
                bad.append(("events", path.name, line_number, reason, detail, line, now))
            else:
                good.append(
                    (
                        event.event_id,
                        event.occurred_at.replace(tzinfo=None),
                        event.account_id,
                        event.user_id,
                        event.event_name,
                        json.dumps(event.properties),
                        now,
                        path.name,
                    )
                )

    if good:
        _append(con, "bronze.events", good)
    if bad:
        _append(con, "bronze.dead_letter", bad)
        _write_dead_letter_file(data_dir / "dead_letter" / "events" / path.name, bad)
    log_row = [path.name, now, len(good), len(bad)]
    con.execute("INSERT INTO bronze._load_log VALUES (?, ?, ?, ?)", log_row)
    return len(good), len(bad)


def load_snapshot(con: duckdb.DuckDBPyConnection, table: str, path: Path) -> int:
    """Replace a bronze table with the current contents of a CSV file, unchanged.

    The CSV format is stated explicitly (comma, double quotes). Letting the database
    guess it from the first rows works until the first value that contains a comma.
    """
    con.execute(
        f"""
        CREATE OR REPLACE TABLE bronze.{table} AS
        SELECT *, now()::TIMESTAMP AS _ingested_at, '{path.name}' AS _source_file
        FROM read_csv(
            '{path.as_posix()}', header = true, all_varchar = true,
            delim = ',', quote = '"', escape = '"'
        )
        """
    )
    return con.execute(f"SELECT count(*) FROM bronze.{table}").fetchone()[0]


def load_mailbox(con: duckdb.DuckDBPyConnection, folder: Path) -> int:
    """Each reply is one small JSON file. Load them all into bronze.mailbox, as text."""
    messages = []
    for path in sorted(folder.glob("*.json")):
        message = json.loads(path.read_text(encoding="utf-8"))
        message["_source_file"] = path.name
        messages.append(message)
    frame = pd.DataFrame(messages).astype("string")  # noqa: F841 (read by DuckDB below)
    con.execute(
        """
        CREATE OR REPLACE TABLE bronze.mailbox AS
        SELECT *, now()::TIMESTAMP AS _ingested_at FROM frame
        """
    )
    return len(messages)


def _append(con: duckdb.DuckDBPyConnection, table: str, rows: list[tuple]) -> None:
    """Append rows to a table in one go (much faster than one INSERT per row)."""
    frame = pd.DataFrame(rows)  # noqa: F841 (read by DuckDB below)
    con.execute(f"INSERT INTO {table} SELECT * FROM frame")


def _write_dead_letter_file(path: Path, bad: list[tuple]) -> None:
    """Keep rejected lines on disk too, next to the reason, so they can be fixed and replayed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        for _source, source_file, line_number, reason, detail, raw, _now in bad:
            record = {
                "source_file": source_file,
                "line_number": line_number,
                "reason": reason,
                "detail": detail,
                "raw": raw,
            }
            f.write(json.dumps(record) + "\n")


if __name__ == "__main__":
    run_ingest()
