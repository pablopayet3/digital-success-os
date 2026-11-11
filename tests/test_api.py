"""Tests for the API (Phase 7). Synthetic data, fictional company.

The API is called in-process with FastAPI's test client, against the small simulated
world. No server is started and no network is used.
"""

import json

import pytest
from fastapi.testclient import TestClient

from api.main import app
from common.store import open_store


@pytest.fixture()
def client(simulated, monkeypatch):
    _, data_dir = simulated
    monkeypatch.setenv("DSO_DATA_DIR", str(data_dir))
    monkeypatch.delenv("API_TOKEN", raising=False)
    return TestClient(app)


def test_health_says_what_you_are_looking_at(client):
    body = client.get("/health").json()
    assert body["status"] == "ok" and "Synthetic data" in body["data"]
    assert body["data_as_of"] and body["llm_mode"]


def test_events_are_validated_and_bad_ones_are_kept_with_a_reason(client, simulated):
    _, data_dir = simulated
    good = {"event_id": "api-test-1", "occurred_at": "2026-09-01T10:00:00", "account_id": "A0001",
            "user_id": "U1", "event_name": "user_active", "properties": {}}  # fmt: skip
    missing_account = {**good, "event_id": "api-test-2", "account_id": ""}
    unknown_event = {**good, "event_id": "api-test-3", "event_name": "made_up_event"}
    body = client.post("/events", json=[good, missing_account, unknown_event]).json()
    assert (body["accepted"], body["rejected"]) == (1, 2)
    assert len(body["rejected_by_reason"]) == 2
    landed = sorted((data_dir / "landing" / "events").glob("api-*.jsonl"))
    assert json.loads(landed[-1].read_text().splitlines()[0])["event_id"] == "api-test-1"
    assert list((data_dir / "dead_letter" / "api").glob("api-*.jsonl"))
    for path in landed:  # leave the landing folder as the other tests expect it
        path.unlink()


def test_writing_endpoints_need_the_token_when_one_is_set(client, monkeypatch):
    monkeypatch.setenv("API_TOKEN", "test-token")
    assert client.post("/events", json=[]).status_code == 401
    assert client.post("/events", json=[], headers={"X-API-Token": "test-token"}).status_code == 200
    assert client.get("/health").status_code == 200  # reading stays open


def test_resolving_a_task_sends_the_return_signal(client, simulated):
    _, data_dir = simulated
    store = open_store(data_dir)
    task = store.one("SELECT * FROM ctas WHERE status <> 'resolved' ORDER BY cta_id")
    if task is None:
        pytest.skip("the small world has no open task right now")
    body = client.post(
        f"/cta/{task['cta_id']}/resolve", json={"outcome": "resolved", "notes": "Called."}
    ).json()
    assert body["next_state"]
    after = store.one("SELECT * FROM ctas WHERE cta_id = :id", id=task["cta_id"])
    assert after["status"] == "resolved" and after["resolved_by"] == "api"
    again = client.post(f"/cta/{task['cta_id']}/resolve", json={"outcome": "resolved"})
    assert again.status_code == 400  # already resolved


def test_an_unknown_outcome_is_refused(client):
    assert (
        client.post("/cta/CTA-does-not-exist/resolve", json={"outcome": "resolved"}).status_code
        == 400
    )


def test_an_inbound_reply_is_classified_and_routed(client, simulated):
    _, data_dir = simulated
    store = open_store(data_dir)
    import duckdb

    from ingest.load import warehouse_path

    con = duckdb.connect(str(warehouse_path(data_dir)))
    email = con.execute(
        """
        SELECT contacts.email FROM gold.dim_contact AS contacts
        JOIN gold.account_current AS accounts ON contacts.account_id = accounts.account_id
        WHERE contacts.can_email LIMIT 1
        """
    ).fetchone()[0]
    con.close()
    reply = {
        "from_email": email,
        "subject": "Re: your email",
        "body": "Please unsubscribe me from these emails.",
    }
    body = client.post("/mailbox/inbound", json=reply).json()
    assert body["intent"] == "unsubscribe" and body["action"] == "opted_out"
    assert store.one("SELECT * FROM mailbox_triage WHERE message_id = :id", id=body["message_id"])
    unknown = client.post(
        "/mailbox/inbound", json={**reply, "from_email": "nobody@nowhere.example"}
    )
    assert unknown.status_code == 404


def test_exports_cover_every_account(client, simulated):
    crm = client.get("/export/crm").json()
    assert len(crm) > 100 and {"account_id", "health_score", "signals_firing", "open_tasks"} <= set(
        crm[0]
    )
    platform = client.get("/export/cs-platform").json()
    assert len(platform["companies"]) == len(crm)
    assert set(platform["companies"][0]["Scorecard Measures"]) == {
        "Adoption",
        "Engagement",
        "Sentiment",
        "Support",
        "Commercial",
    }


def test_log_lines_are_json(capsys):
    from common.logs import get_logger

    get_logger("test").info("request", extra={"fields": {"path": "/health", "status": 200}})
    line = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert line["message"] == "request" and line["status"] == 200 and line["level"] == "info"
