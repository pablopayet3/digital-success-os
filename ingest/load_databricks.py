"""Load the landing files into Databricks (the prod warehouse).

Synthetic data, fictional company.

STATUS: run against a real Free Edition workspace (docs/decisions/0012). It needs
DATABRICKS_HOST and DATABRICKS_HTTP_PATH; sign-in is through the browser unless
DATABRICKS_TOKEN is set.

Same rules as the local loader (ingest/load.py), different mechanics:

  1. Events are validated here, with the same pydantic check as in dev. Good events
     and rejected events are written to two files.
  2. Every landing file is uploaded to a Unity Catalog volume
     (/Volumes/relay/bronze/landing). The volume is the landing zone in prod.
  3. Bronze tables are created from the files in the volume with read_files().

Bronze is rebuilt from the volume on every run. That is fine at this size
(about 500,000 events). At scale the same step becomes an incremental load
(Auto Loader or COPY INTO), which only reads files it has not seen.
"""

from __future__ import annotations

import json
from pathlib import Path

from common.paths import DATA_DIR
from common.warehouse import DatabricksWarehouse
from ingest.load import SNAPSHOT_FILES
from ingest.schemas import validate_event

EVENT_COLUMNS = (
    "event_id string, occurred_at string, account_id string, user_id string, "
    "event_name string, properties string, _source_file string"
)
DEAD_LETTER_COLUMNS = (
    "source string, source_file string, line_number int, reason string, "
    "detail string, raw string"
)


def run_ingest_databricks(warehouse: DatabricksWarehouse, data_dir: Path = DATA_DIR) -> dict:
    """Validate, upload and load everything. Returns what it did."""
    landing = data_dir / "landing"
    staging = data_dir / "staging"
    staging.mkdir(parents=True, exist_ok=True)

    warehouse.execute("CREATE SCHEMA IF NOT EXISTS bronze")
    warehouse.execute("CREATE VOLUME IF NOT EXISTS bronze.landing")

    # 1. Validate events locally: one file of good events, one of rejected ones.
    good_path, bad_path = staging / "events_valid.jsonl", staging / "dead_letter.jsonl"
    loaded = rejected = 0
    with (
        open(good_path, "w", encoding="utf-8") as good,
        open(bad_path, "w", encoding="utf-8") as bad,
    ):
        for path in sorted((landing / "events").glob("*.jsonl")):
            with open(path, encoding="utf-8") as lines:
                for line_number, line in enumerate(lines, start=1):
                    line = line.rstrip("\n")
                    event, reason, detail = validate_event(line)
                    if event is None:
                        record = {
                            "source": "events", "source_file": path.name,
                            "line_number": line_number, "reason": reason,
                            "detail": detail, "raw": line,
                        }  # fmt: skip
                        bad.write(json.dumps(record) + "\n")
                        rejected += 1
                    else:
                        row = json.loads(line)
                        row["_source_file"] = path.name
                        good.write(json.dumps(row) + "\n")
                        loaded += 1

    # 2. Upload to the volume, and 3. create the bronze tables from the files.
    events_file = warehouse.upload(good_path, "events_valid/events.jsonl")
    dead_file = warehouse.upload(bad_path, "dead_letter/dead_letter.jsonl")
    warehouse.execute(
        f"""
        CREATE OR REPLACE TABLE bronze.events AS
        SELECT event_id, CAST(occurred_at AS TIMESTAMP) AS occurred_at, account_id, user_id,
               event_name, properties, current_timestamp() AS _ingested_at, _source_file
        FROM read_files('{events_file}', format => 'json', schema => '{EVENT_COLUMNS}')
        """
    )
    warehouse.execute(
        f"""
        CREATE OR REPLACE TABLE bronze.dead_letter AS
        SELECT *, current_timestamp() AS _ingested_at
        FROM read_files('{dead_file}', format => 'json', schema => '{DEAD_LETTER_COLUMNS}')
        """
    )

    summary = {"events_loaded": loaded, "events_rejected": rejected}
    for table, file_name in SNAPSHOT_FILES.items():
        uploaded = warehouse.upload(landing / file_name, file_name)
        warehouse.execute(
            f"""
            CREATE OR REPLACE TABLE bronze.{table} AS
            SELECT *, current_timestamp() AS _ingested_at, '{file_name}' AS _source_file
            FROM read_files(
                '{uploaded}', format => 'csv', header => true, inferSchema => false,
                multiLine => true, schemaEvolutionMode => 'none'
            )
            """
        )
        summary[table] = int(warehouse.query(f"SELECT count(*) AS n FROM bronze.{table}")["n"][0])

    # Mailbox replies: many small JSON files become one file with one message per line.
    mailbox_path = staging / "mailbox.jsonl"
    messages = sorted((landing / "mailbox").glob("*.json"))
    with open(mailbox_path, "w", encoding="utf-8") as out:
        for path in messages:
            message = json.loads(path.read_text(encoding="utf-8"))
            message["_source_file"] = path.name
            out.write(json.dumps(message) + "\n")
    mailbox_file = warehouse.upload(mailbox_path, "mailbox/mailbox.jsonl")
    warehouse.execute(
        f"""
        CREATE OR REPLACE TABLE bronze.mailbox AS
        SELECT *, current_timestamp() AS _ingested_at
        FROM read_files('{mailbox_file}', format => 'json', schemaEvolutionMode => 'none')
        """
    )
    summary["mailbox"] = len(messages)
    return summary
