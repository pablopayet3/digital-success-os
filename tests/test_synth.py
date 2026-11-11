"""Tests for the synthetic world generator (Phase 1). Synthetic data, fictional company.

They run on the "small" profile (250 accounts, 120 days) so the whole file takes
a few seconds.
"""

import hashlib
import json
import re
from collections import Counter
from pathlib import Path

import pandas as pd
import pytest

from synth.generate import (
    ACCOUNT_COLUMNS,
    CONTACT_COLUMNS,
    EMAIL_COLUMNS,
    LICENSE_COLUMNS,
    MAILBOX_FIELDS,
    NPS_COLUMNS,
    OPPORTUNITY_COLUMNS,
    TICKET_COLUMNS,
    generate,
)
from synth.world import World

KNOWN_EVENTS = {
    "user_invited", "user_active", "board_created", "doc_published",
    "automation_rule_created", "integration_connected", "sso_configured",
    "assist_invoked", "admin_login",
}  # fmt: skip

# Hidden traits and answer-key fields. None of these may appear in a landing file.
HIDDEN_NAMES = {
    "engagement", "engagement_propensity", "fit", "growth", "docs_need", "setup_drive",
    "assist_affinity", "momentum", "team_size", "setback", "friction_days_left", "affinity",
    "has_left", "churn_hazard", "intent", "sentiment", "is_hard", "tone",
}  # fmt: skip

# Real brands that must never appear in the demo data.
REAL_BRANDS = [
    "atlassian", "jira", "confluence", "trello", "rovo", "gainsight", "salesforce",
    "databricks", "tableau", "slack", "github", "google", "microsoft", "okta", "zoom",
]  # fmt: skip


@pytest.fixture(scope="session")
def small_world(tmp_path_factory):
    data_dir = tmp_path_factory.mktemp("data")
    world = generate(profile="small", data_dir=data_dir, verbose=False)
    return world, data_dir


@pytest.fixture(scope="session")
def landing(small_world) -> Path:
    return small_world[1] / "landing"


@pytest.fixture(scope="session")
def truth(small_world) -> Path:
    return small_world[1] / "ground_truth"


@pytest.fixture(scope="session")
def event_lines(landing) -> list[str]:
    lines = []
    for path in sorted((landing / "events").glob("*.jsonl")):
        lines += path.read_text(encoding="utf-8").splitlines()
    return lines


@pytest.fixture(scope="session")
def events(event_lines) -> list[dict]:
    """Every event line that is valid JSON."""
    parsed = []
    for line in event_lines:
        try:
            parsed.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return parsed


def _file_hashes(folder: Path) -> dict[str, str]:
    return {
        str(path.relative_to(folder)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(folder.rglob("*"))
        if path.is_file() and path.suffix != ".pkl"
    }


def test_same_seed_gives_identical_files(small_world, tmp_path):
    _, first_dir = small_world
    generate(profile="small", data_dir=tmp_path, verbose=False)
    assert _file_hashes(first_dir) == _file_hashes(tmp_path)


def test_files_have_expected_columns(landing):
    expected = {
        "crm_accounts.csv": ACCOUNT_COLUMNS,
        "crm_contacts.csv": CONTACT_COLUMNS,
        "crm_opportunities.csv": OPPORTUNITY_COLUMNS,
        "licenses.csv": LICENSE_COLUMNS,
        "tickets.csv": TICKET_COLUMNS,
        "nps.csv": NPS_COLUMNS,
        "email_engagement.csv": EMAIL_COLUMNS,
    }
    for name, columns in expected.items():
        frame = pd.read_csv(landing / name)
        assert list(frame.columns) == columns, name
        assert len(frame) > 0, name
    message = json.loads(next((landing / "mailbox").glob("*.json")).read_text(encoding="utf-8"))
    assert list(message) == MAILBOX_FIELDS


def test_ids_are_unique(landing, truth, events):
    keys = {
        "crm_accounts.csv": "account_id",
        "crm_contacts.csv": "contact_id",
        "crm_opportunities.csv": "opportunity_id",
        "tickets.csv": "ticket_id",
        "nps.csv": "response_id",
        "email_engagement.csv": "send_id",
    }
    for name, key in keys.items():
        assert pd.read_csv(landing / name)[key].is_unique, name

    # Events: the only repeated ids are the ones injected on purpose, each exactly twice.
    issues = json.loads((truth / "injected_issues.json").read_text())
    counts = Counter(event["event_id"] for event in events)
    repeated = {event_id for event_id, n in counts.items() if n > 1}
    assert repeated == set(issues["duplicate_event_id"])
    assert all(counts[event_id] == 2 for event_id in repeated)


def test_records_point_to_real_accounts(landing, events):
    accounts = set(pd.read_csv(landing / "crm_accounts.csv")["account_id"])
    for name in ("crm_contacts.csv", "crm_opportunities.csv", "licenses.csv", "tickets.csv",
                 "nps.csv", "email_engagement.csv"):  # fmt: skip
        assert set(pd.read_csv(landing / name)["account_id"]) <= accounts, name

    contacts = set(pd.read_csv(landing / "crm_contacts.csv")["contact_id"])
    assert set(pd.read_csv(landing / "tickets.csv")["contact_id"]) <= contacts
    assert set(pd.read_csv(landing / "nps.csv")["contact_id"]) <= contacts

    event_accounts = {e["account_id"] for e in events if e["account_id"] is not None}
    assert event_accounts <= accounts

    sends = set(pd.read_csv(landing / "email_engagement.csv")["send_id"])
    for path in (landing / "mailbox").glob("*.json"):
        assert json.loads(path.read_text(encoding="utf-8"))["in_reply_to"] in sends


def test_no_hidden_fields_in_landing_files(landing, events):
    for path in landing.glob("*.csv"):
        columns = set(pd.read_csv(path, nrows=1).columns)
        assert not columns & HIDDEN_NAMES, path.name
    for event in events[:5000]:
        assert not (set(event) | set(event["properties"])) & HIDDEN_NAMES
    for path in (landing / "mailbox").glob("*.json"):
        assert not set(json.loads(path.read_text(encoding="utf-8"))) & HIDDEN_NAMES


def test_hidden_traits_drive_outcomes(truth):
    """The models can only find patterns that the simulator really put there."""
    latents = pd.read_csv(truth / "latents.csv")
    hidden = pd.read_csv(truth / "daily_hidden_state.csv")
    outcomes = pd.read_csv(truth / "outcomes.csv")

    # Poorly fitting accounts carry a clearly higher daily risk of churning.
    risk = hidden.groupby("account_id")["churn_hazard"].mean().rename("risk").reset_index()
    by_fit = latents.merge(risk, on="account_id").sort_values("fit")
    third = len(by_fit) // 3
    assert by_fit["risk"].head(third).mean() > 2 * by_fit["risk"].tail(third).mean()

    # And the accounts that did churn fit worse, on average, than those that stayed.
    merged = latents.merge(outcomes, on="account_id")
    churned = merged[merged["churned_at"].notna()]
    stayed = merged[merged["churned_at"].isna()]
    assert len(churned) >= 5
    assert churned["fit"].mean() < stayed["fit"].mean()


def test_injected_problems_match_the_issue_log(small_world, landing, truth, event_lines, events):
    world, _ = small_world
    issues = json.loads((truth / "injected_issues.json").read_text())

    assert len(event_lines) - len(events) == issues["malformed_lines"] > 0
    missing = [e["event_id"] for e in events if e["account_id"] is None]
    assert sorted(missing) == sorted(issues["missing_account_id"])
    unknown = [e["event_id"] for e in events if e["event_name"] not in KNOWN_EVENTS]
    assert sorted(unknown) == sorted(issues["unknown_event_name"])
    last_day = world.last_day.isoformat()
    future = [e["event_id"] for e in events if e["occurred_at"][:10] > last_day]
    assert sorted(future) == sorted(issues["future_timestamp"])

    # The late day: most of its events sit in the file of a later day.
    late = issues["late_arriving"]
    own_file = (landing / "events" / f"{late['event_date']}.jsonl").read_text(encoding="utf-8")
    on_time = sum(1 for line in own_file.splitlines() if late["event_date"] in line)
    assert late["late_events"] > on_time

    contacts = pd.read_csv(landing / "crm_contacts.csv")
    duplicates = contacts[contacts["contact_id"].str.endswith("-DUP")]
    assert sorted(duplicates["contact_id"]) == sorted(issues["duplicate_contact_email"])
    assert contacts["email"].str.lower().duplicated().sum() >= len(duplicates) > 0
    standard_personas = {"admin", "billing", "champion", "end_user"}
    originals = contacts[~contacts["contact_id"].str.endswith("-DUP")]
    assert (~originals["persona"].isin(standard_personas)).sum() == issues["messy_persona"]


def test_no_real_brand_names(landing):
    pattern = re.compile(r"\b(" + "|".join(REAL_BRANDS) + r")\b")
    for path in landing.rglob("*"):
        if path.is_file():
            found = pattern.search(path.read_text(encoding="utf-8").lower())
            assert found is None, f"{found.group()} found in {path.name}"


def test_mailbox_covers_every_intent(landing, truth):
    labels = pd.read_csv(truth / "mailbox_labels.csv")
    assert set(labels["intent"]) == {
        "out_of_office", "unsubscribe", "left_company", "product_question",
        "buying_intent", "complaint", "meeting_request",
    }  # fmt: skip
    files = {path.stem for path in (landing / "mailbox").glob("*.json")}
    assert files == set(labels["message_id"])


def test_churned_accounts_stop_sending_events(landing, events):
    accounts = pd.read_csv(landing / "crm_accounts.csv")
    churned = accounts[accounts["status"] == "churned"].set_index("account_id")["churned_at"]
    assert len(churned) > 0
    last_event = {}
    for event in events:
        account, day = event["account_id"], event["occurred_at"][:10]
        if account in churned.index and day[:4] == "2026":  # ignore the wrong-clock events
            last_event[account] = max(last_event.get(account, ""), day)
    assert all(day <= churned[account] for account, day in last_event.items())


def test_world_can_be_saved_and_continued(small_world, truth):
    """Phase 4 moves the world forward one day at a time; check that this works."""
    world, _ = small_world
    resumed = World.load(truth / "world_state.pkl")
    assert resumed.day_index == world.day_index

    next_day = resumed.today
    out = resumed.step()
    assert out.date == next_day
    assert len(out.events) > 0
    assert all(event["occurred_at"].startswith(next_day.isoformat()) for event in out.events)
    assert resumed.day_index == world.day_index + 1
