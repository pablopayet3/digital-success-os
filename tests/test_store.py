"""Tests for the operational store, on every database it is meant to run on.

Synthetic data, fictional company. SQLite always. Postgres too, when the
DSO_TEST_POSTGRES_URL variable points at one (the CI job `store-on-postgres` starts a
real Postgres for this). The same tests, so the two cannot drift apart.
"""

import os

import pytest
from sqlalchemy import text

from common.store import TABLES, Store

BACKENDS = ["sqlite"] + (["postgres"] if os.environ.get("DSO_TEST_POSTGRES_URL") else [])


@pytest.fixture(params=BACKENDS)
def store(request, tmp_path) -> Store:
    """An empty store on the requested database."""
    if request.param == "sqlite":
        return Store(f"sqlite:///{(tmp_path / 'ops.db').as_posix()}")
    fresh = Store(os.environ["DSO_TEST_POSTGRES_URL"])
    with fresh.engine.begin() as con:  # the database is shared between tests: empty it
        for table in TABLES:
            con.execute(text(f"DELETE FROM {table}"))
    return fresh


def cta(cta_id: str, **changes) -> dict:
    row = {
        "cta_id": cta_id, "account_id": "A0001", "contact_id": None, "play_id": "usage_recovery",
        "enrollment_id": None, "step_id": None, "source": "journey", "queue": "pooled_csm",
        "priority": "high", "reason_code": "usage_drop_needs_human", "title": "Usage is falling",
        "packet": "{}", "status": "open", "created_on": "2026-09-01", "sla_due_on": "2026-09-03",
        "picked_up_on": None, "resolved_on": None, "outcome": None, "outcome_notes": None,
        "resolved_by": None, "next_state": None,
    }  # fmt: skip
    return {**row, **changes}


def test_every_table_exists_with_its_columns(store):
    for table in TABLES:
        assert store.rows(f"SELECT * FROM {table}") == []
        assert len(store.table(table).columns) >= 4


def test_rows_go_in_and_come_back_with_their_types(store):
    store.insert("ctas", cta("CTA-00001"), cta("CTA-00002", priority="low"))
    store.insert(
        "queue_alerts",
        {"alert_date": "2026-09-01", "queue": "sales", "open_ctas": 31,
         "capacity_per_day": 15, "message": "Sales: 31 open, capacity 15 a day."},
    )  # fmt: skip
    assert store.one("SELECT count(*) AS n FROM ctas")["n"] == 2
    assert store.one("SELECT open_ctas FROM queue_alerts")["open_ctas"] == 31
    assert store.one("SELECT picked_up_on FROM ctas WHERE cta_id = :id", id="CTA-00001") == {
        "picked_up_on": None
    }


def test_update_changes_only_the_matching_row(store):
    store.insert("ctas", cta("CTA-00001"), cta("CTA-00002"))
    store.update("ctas", {"cta_id": "CTA-00002"}, status="resolved", outcome="saved")
    statuses = {r["cta_id"]: r["status"] for r in store.rows("SELECT cta_id, status FROM ctas")}
    assert statuses == {"CTA-00001": "open", "CTA-00002": "resolved"}


def test_ids_count_up(store):
    assert store.next_id("ctas", "CTA") == "CTA-00001"
    store.insert("ctas", cta("CTA-00001"))
    assert store.next_id("ctas", "CTA") == "CTA-00002"


def test_dates_as_text_sort_and_compare_like_dates(store):
    store.insert("ctas", cta("CTA-00001", sla_due_on="2026-09-03"), cta("CTA-00002", sla_due_on="2026-10-01"))
    due = store.rows("SELECT cta_id FROM ctas WHERE sla_due_on <= :day ORDER BY sla_due_on", day="2026-09-15")
    assert [row["cta_id"] for row in due] == ["CTA-00001"]


def test_grouped_counts_work_the_same_everywhere(store):
    store.insert("ctas", cta("CTA-00001"), cta("CTA-00002"), cta("CTA-00003", queue="sales"))
    counts = store.rows("SELECT queue, count(*) AS n FROM ctas WHERE status <> 'resolved' GROUP BY queue ORDER BY queue")
    assert counts == [{"queue": "pooled_csm", "n": 2}, {"queue": "sales", "n": 1}]


def test_a_store_made_by_an_older_version_gains_new_columns(store):
    store.execute("ALTER TABLE conversations DROP COLUMN answered_by")
    Store(str(store.engine.url.render_as_string(hide_password=False)))._add_new_columns()
    assert "answered_by" in store.table("conversations").columns
