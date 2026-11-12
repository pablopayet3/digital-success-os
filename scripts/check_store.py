"""After a simulated run: is the engine's state really in the store we think it is in?

Synthetic data, fictional company. Used by the CI job that runs the engine with its
operational store on Postgres. Prints the row counts and fails if the run left nothing.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.store import open_store  # noqa: E402

store = open_store()
kind = store.engine.url.get_backend_name()
counts = {
    table: store.one(f"SELECT count(*) AS n FROM {table}")["n"]
    for table in ("enrollments", "audit_log", "touches", "ctas", "mailbox_triage", "conversations")
}
print(f"operational store: {kind}")
for table, rows in counts.items():
    print(f"  {table}: {rows}")
expected = sys.argv[1] if len(sys.argv) > 1 else kind
assert kind == expected, f"expected the store to be {expected}, it is {kind}"
for table in ("enrollments", "audit_log", "ctas", "mailbox_triage"):
    assert counts[table] > 0, f"{table} is empty: the engine did not write to this store"
print("ok: the engine ran on this store")
