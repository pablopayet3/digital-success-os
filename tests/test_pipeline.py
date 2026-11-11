"""Tests for ingest, the dbt models and the data contract (Phase 2).

Synthetic data, fictional company. The generator logs every data problem it
injects. These tests prove the pipeline caught exactly those rows.
"""

import copy
import csv
import json

from common.config import load_world_config
from common.paths import ROOT
from contracts.check import check_contract, load_contract
from ingest.load import run_ingest
from ingest.schemas import validate_event

GOOD_EVENT = {
    "event_id": "ev-1",
    "occurred_at": "2026-05-01T10:00:00Z",
    "account_id": "A0001",
    "user_id": "A0001-u000",
    "event_name": "user_active",
    "properties": {"sessions": 2},
}


def _line(**changes) -> str:
    return json.dumps({**GOOD_EVENT, **changes})


def test_validation_accepts_a_good_event():
    event, reason, _ = validate_event(_line())
    assert reason is None
    assert event.account_id == "A0001"


def test_validation_gives_a_reason_for_each_kind_of_bad_event():
    assert validate_event(_line(account_id=None))[1] == "missing_account_id"
    assert validate_event(_line(account_id="not-an-account"))[1] == "invalid_account_id"
    assert validate_event(_line(event_name="page_view"))[1] == "unknown_event_name"
    assert validate_event(_line(occurred_at="yesterday"))[1] == "invalid_occurred_at"
    assert validate_event('{"event_id": "ev-1", "occurr')[1] == "malformed_json"


def test_pipeline_builds_and_all_data_tests_pass(pipeline, warehouse):
    succeeded, _ = pipeline
    assert succeeded
    statuses = warehouse.execute("SELECT DISTINCT status FROM gold.dq_test_results").fetchall()
    assert statuses == [("pass",)]
    assert warehouse.execute("SELECT status FROM gold.dq_freshness").fetchall() == [("pass",)]


def test_dead_letter_holds_exactly_the_injected_bad_events(warehouse, issues):
    reasons = dict(
        warehouse.execute("SELECT reason, count(*) FROM bronze.dead_letter GROUP BY 1").fetchall()
    )
    assert reasons == {
        "missing_account_id": len(issues["missing_account_id"]),
        "unknown_event_name": len(issues["unknown_event_name"]),
        "malformed_json": issues["malformed_lines"],
    }


def test_dead_letter_files_keep_the_raw_line_and_the_reason(pipeline):
    _, data_dir = pipeline
    files = list((data_dir / "dead_letter" / "events").glob("*.jsonl"))
    assert files
    record = json.loads(files[0].read_text(encoding="utf-8").splitlines()[0])
    assert set(record) == {"source_file", "line_number", "reason", "detail", "raw"}


def test_silver_removes_duplicates_and_future_events(warehouse, issues):
    bronze_rows, bronze_ids = warehouse.execute(
        "SELECT count(*), count(DISTINCT event_id) FROM bronze.events"
    ).fetchone()
    assert bronze_rows - bronze_ids == len(issues["duplicate_event_id"])

    silver_rows, silver_ids = warehouse.execute(
        "SELECT count(*), count(DISTINCT event_id) FROM silver.stg_events"
    ).fetchone()
    assert silver_rows == silver_ids == bronze_ids - len(issues["future_timestamp"])


def test_late_arriving_events_are_kept_under_their_true_date(warehouse, issues):
    late = issues["late_arriving"]
    kept = warehouse.execute(
        """
        SELECT count(*) FROM silver.stg_events
        WHERE event_date = ? AND _source_file NOT LIKE ?
        """,
        [late["event_date"], late["event_date"] + "%"],
    ).fetchone()[0]
    assert 0 < kept <= late["late_events"]


def test_running_ingest_twice_loads_nothing_new(pipeline, warehouse):
    _, data_dir = pipeline
    before = warehouse.execute("SELECT count(*) FROM bronze.events").fetchone()[0]
    summary = run_ingest(data_dir, verbose=False)
    assert summary["event_files_loaded"] == 0
    assert warehouse.execute("SELECT count(*) FROM bronze.events").fetchone()[0] == before


def test_contacts_are_deduplicated_and_personas_normalised(warehouse, issues):
    bronze = warehouse.execute("SELECT count(*) FROM bronze.crm_contacts").fetchone()[0]
    silver = warehouse.execute("SELECT count(*) FROM silver.stg_contacts").fetchone()[0]
    assert bronze - silver == len(issues["duplicate_contact_email"])

    normalised = warehouse.execute(
        "SELECT count(*) FROM silver.stg_contacts WHERE persona_raw <> persona"
    ).fetchone()[0]
    assert normalised == issues["messy_persona"]
    rows, people = warehouse.execute(
        "SELECT count(*), count(DISTINCT (account_id, email)) FROM silver.stg_contacts"
    ).fetchone()
    assert rows == people


def test_gold_table_measures_what_really_happened(current_world, warehouse):
    """Seats and setup progress in gold match the simulator's own state."""
    world = current_world
    rows = warehouse.execute(
        """
        SELECT account_id, seats_assigned, prerequisite_closure_pct
        FROM gold.account_daily
        WHERE snapshot_date = (SELECT max(snapshot_date) FROM gold.account_daily)
        """
    ).fetchall()
    truth = {a.account_id: a for a in world.accounts}
    assert len(rows) > 100

    # Seats come from the system of record, so they are always exact.
    assert all(truth[account_id].seats_assigned == seats for account_id, seats, _ in rows)

    # Setup progress is read from events. A few events were rejected at ingest,
    # so a small share of accounts may look one step behind.
    closure_match = sum(
        1 for account_id, _, closure in rows if len(truth[account_id].setup_done) / 4 == closure
    )
    assert closure_match / len(rows) > 0.95


def test_contract_holds_for_the_live_table(pipeline):
    _, data_dir = pipeline
    broken = [check for check in check_contract(data_dir, save=False) if not check["passed"]]
    assert broken == []


def test_contract_check_notices_a_broken_promise(pipeline):
    _, data_dir = pipeline
    contract = copy.deepcopy(load_contract())
    contract["columns"][0]["type"] = "integer"  # account_id is text, not a number
    contract["columns"].append(
        {"name": "column_that_does_not_exist", "type": "text", "nullable": True, "description": ""}
    )
    failed = {c["check"] for c in check_contract(data_dir, contract, save=False) if not c["passed"]}
    assert failed == {"columns: none missing", "columns: types match"}


def test_edition_limits_seed_matches_the_generator_config():
    """The warehouse and the simulator must agree on what each edition includes."""
    editions = load_world_config()["editions"]
    with open(ROOT / "dbt" / "seeds" / "edition_limits.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            config = editions[row["edition"]]
            assert int(row["automation_rule_limit"]) == config["automation_rules"]
            assert int(row["integration_limit"]) == config["integrations"]
            assert int(row["assist_credits_per_seat"]) == config["assist_credits_per_seat"]
