"""Fill an empty hosted operational store with the demo's state. Runs when a service starts.

Synthetic data, fictional company.

The container image carries a small demo world whose live state (enrolments, tasks,
conversations) sits in a local SQLite file. When the host gives the services a Postgres
database instead, that database starts empty. This copies the demo state into it, once.

Rules:
  - If the store is the local file, there is nothing to do.
  - If the hosted store already has data, nothing is touched.
  - Two services start at the same time, so the copy holds a database lock: only one of
    them copies, the other finds the data there.

Exit code 0 means the hosted store is ready (or not in use). Any other code tells the
start script to fall back to the local file, so the demo still comes up.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402

from common.paths import DATA_DIR  # noqa: E402
from common.store import TABLES, Store, open_store  # noqa: E402

SEED_LOCK = 4242  # any fixed number: it only has to be the same in every service


def seed() -> str:
    target = open_store()
    if target.engine.url.get_backend_name() == "sqlite":
        return "the store is the local file: nothing to seed"
    source_file = DATA_DIR / "ops.db"
    if not source_file.exists():
        return "no demo state in this image: the hosted store stays empty"
    source = Store(f"sqlite:///{source_file.as_posix()}")

    with target.engine.begin() as con:
        con.execute(text(f"SELECT pg_advisory_xact_lock({SEED_LOCK})"))
        if con.execute(text("SELECT count(*) FROM enrollments")).scalar():
            return "the hosted store already has data: left as it is"
        copied = 0
        for table in TABLES:
            rows = source.rows(f"SELECT * FROM {table}")
            if not rows:
                continue
            names = list(rows[0])
            placeholders = ", ".join(f":{name}" for name in names)
            con.execute(
                text(f"INSERT INTO {table} ({', '.join(names)}) VALUES ({placeholders})"), rows
            )
            copied += len(rows)
    return f"copied {copied} rows of demo state into the hosted store"


if __name__ == "__main__":
    print("seed_store:", seed())
