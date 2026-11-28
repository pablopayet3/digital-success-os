"""Tests for the CRM sync. Synthetic data, fictional company.

No CRM is contacted: a small stand-in records what would be sent. What is tested is
ours: the mapping, and that running twice does not create anything twice.
"""

import json

from integrations.crm_sync import build_payloads, dry_run, push


class FakeObject:
    def __init__(self, crm, name):
        self.crm, self.name = crm, name

    def create(self, fields):
        record_id = f"{self.name[:3].upper()}{len(self.crm.records[self.name]) + 1:04d}"
        self.crm.records[self.name][record_id] = dict(fields)
        return {"id": record_id}

    def update(self, record_id, fields):
        self.crm.records[self.name][record_id].update(fields)


class FakeCrm:
    """Just enough of a CRM: two objects and the two lookups the sync makes."""

    def __init__(self):
        self.records = {"Account": {}, "Task": {}}
        self.Account, self.Task = FakeObject(self, "Account"), FakeObject(self, "Task")
        self.base_url = "https://acme-dev-ed.develop.my.salesforce.com/services/data/v59.0/"

    def query(self, soql):
        if "FROM Account" in soql:
            number = soql.split("AccountNumber = '")[1].split("'")[0]
            ids = [i for i, r in self.records["Account"].items() if r["AccountNumber"] == number]
        elif "WHERE Id = '" in soql:
            wanted = soql.split("WHERE Id = '")[1].split("'")[0]
            ids = [wanted] if wanted in self.records["Task"] else []
        else:
            what = soql.split("WhatId = '")[1].split("'")[0] if "WhatId" in soql else None
            marker = soql.split("LIKE '")[1].split("%")[0]
            ids = [
                i for i, r in self.records["Task"].items()
                if what in (None, r["WhatId"]) and r["Subject"].startswith(marker)
            ]  # fmt: skip
        found = [{"Id": i, **self.records["Task"].get(i, {})} for i in ids[:1]]
        return {"records": found}


def test_payloads_cover_accounts_with_open_tasks_and_say_the_data_is_synthetic(simulated):
    _, data_dir = simulated
    payloads = build_payloads(data_dir)
    assert payloads, "the simulated world should have open tasks"
    for payload in payloads:
        account, tasks = payload["account"], payload["tasks"]
        assert account["AccountNumber"].startswith("A") and "Health" in account["Description"]
        assert "Synthetic data" in account["Description"] and tasks
        for task in tasks:
            assert task["Subject"].startswith("[CTA-")
            assert task["Priority"] in ("High", "Normal", "Low")


def test_the_dry_run_writes_exactly_what_would_be_sent(simulated, tmp_path):
    _, data_dir = simulated
    counts = dry_run(data_dir, tmp_path)
    written = json.loads((tmp_path / "payloads.json").read_text(encoding="utf-8"))
    assert counts["accounts"] == len(written) > 0
    assert counts["tasks"] == sum(len(p["tasks"]) for p in written)


def test_pushing_twice_updates_accounts_and_creates_no_duplicate_task(simulated):
    _, data_dir = simulated
    payloads, crm = build_payloads(data_dir), FakeCrm()
    first = push(crm, payloads)
    second = push(crm, payloads)
    assert first["accounts_created"] == len(payloads) and first["accounts_updated"] == 0
    assert second["accounts_created"] == 0 and second["accounts_updated"] == len(payloads)
    assert second["tasks_created"] == 0 and second["tasks_kept"] == first["tasks_created"] > 0
    assert len(crm.records["Task"]) == first["tasks_created"]
    linked = {task["WhatId"] for task in crm.records["Task"].values()}
    assert linked <= set(crm.records["Account"])  # every task hangs on a real account


def test_an_expansion_task_carries_the_account_owner_brief(simulated):
    """What the seller opens in the CRM must hold the brief, not a link back to our system."""
    from common.store import open_store
    from integrations.crm_sync import task_fields

    _, data_dir = simulated
    tasks = open_store(data_dir).rows("SELECT * FROM ctas")
    with_brief = [task for task in tasks if json.loads(task["packet"]).get("brief")]
    assert with_brief, "the simulated world should have a Sales task with a brief"
    brief = json.loads(with_brief[0]["packet"])["brief"]
    description = task_fields(with_brief[0])["Description"]
    assert "BRIEF FOR THE ACCOUNT OWNER" in description
    assert all(f"• {line.strip()}" in description for line in brief.splitlines() if line.strip())


# --- Signing in ----------------------------------------------------------------------------------

EVERY_SETTING = (
    "SALESFORCE_CONSUMER_KEY", "SALESFORCE_CONSUMER_SECRET", "SALESFORCE_DOMAIN",
    "SALESFORCE_USERNAME", "SALESFORCE_PASSWORD", "SALESFORCE_SECURITY_TOKEN",
    "SALESFORCE_CLI_ORG",
)  # fmt: skip


def sign_in_with(monkeypatch, **settings) -> dict:
    """Call connect() with only these settings, and return what the library was given."""
    import simple_salesforce

    from integrations.crm_sync import connect

    for name in EVERY_SETTING:
        monkeypatch.delenv(name, raising=False)
    for name, value in settings.items():
        monkeypatch.setenv(name, value)
    given = {}
    monkeypatch.setattr(simple_salesforce, "Salesforce", lambda **kwargs: given.update(kwargs))
    connect()
    return given


def test_a_consumer_key_signs_in_at_the_orgs_own_address(monkeypatch):
    given = sign_in_with(
        monkeypatch,
        SALESFORCE_CONSUMER_KEY="key",
        SALESFORCE_CONSUMER_SECRET="secret",
        SALESFORCE_DOMAIN="https://acme-dev-ed.develop.my.salesforce.com/",
        SALESFORCE_USERNAME="left over from an earlier try",
    )
    assert given == {
        "consumer_key": "key", "consumer_secret": "secret", "domain": "acme-dev-ed.develop.my",
    }  # fmt: skip


def test_a_username_and_token_sign_in_at_the_general_address(monkeypatch):
    given = sign_in_with(
        monkeypatch,
        SALESFORCE_USERNAME="someone@example.com",
        SALESFORCE_PASSWORD="a password",
        SALESFORCE_SECURITY_TOKEN="a token",
    )
    assert given["username"] == "someone@example.com" and given["domain"] == "login"
    assert "consumer_key" not in given


def test_half_a_set_of_credentials_is_refused_with_the_names_to_add(monkeypatch):
    import pytest

    with pytest.raises(RuntimeError, match="SALESFORCE_CONSUMER_KEY.*SALESFORCE_USERNAME"):
        sign_in_with(monkeypatch, SALESFORCE_USERNAME="someone@example.com")


def test_the_orgs_address_is_understood_however_it_is_pasted():
    from integrations.crm_sync import explain_refusal, my_domain

    wanted = "acme-dev-ed.develop.my"
    assert my_domain("https://acme-dev-ed.develop.my.salesforce.com/") == wanted
    assert my_domain("acme-dev-ed.develop.lightning.force.com") == wanted
    assert my_domain(" acme-dev-ed.develop.my ") == wanted
    assert my_domain("login") == "login"
    assert "Enable SOAP API login()" in explain_refusal(Exception("refused"))


def fake_tool(monkeypatch, output: str, installed: bool = True) -> list:
    """Stand in for the vendor's command-line tool. Returns the commands it was asked to run."""
    import shutil
    import subprocess
    from types import SimpleNamespace

    asked = []

    def run(command, **_):
        asked.append(command)
        return SimpleNamespace(stdout=output, returncode=0)

    monkeypatch.setattr(shutil, "which", lambda name, **_: "sf" if installed else None)
    monkeypatch.setattr(subprocess, "run", run)
    return asked


def test_a_browser_sign_in_is_taken_from_the_command_line_tool(monkeypatch):
    # The stand-in answers every command with both facts; the code picks the one it asked for.
    session = {"result": {"instanceUrl": "https://acme.example", "accessToken": "a-session"}}
    asked = fake_tool(monkeypatch, json.dumps(session))
    given = sign_in_with(monkeypatch, SALESFORCE_CLI_ORG="demo-org")
    assert given == {"instance_url": "https://acme.example", "session_id": "a-session"}
    # Where the org lives comes from one command, the session from another.
    assert asked == [
        ["sf", "org", "display", "--target-org", "demo-org", "--json"],
        ["sf", "org", "auth", "show-access-token", "--target-org", "demo-org", "--json"],
    ]


def test_a_missing_or_signed_out_tool_is_explained_without_showing_its_output(monkeypatch):
    import pytest

    fake_tool(monkeypatch, "", installed=False)
    with pytest.raises(RuntimeError, match="not installed"):
        sign_in_with(monkeypatch, SALESFORCE_CLI_ORG="demo-org")

    # Signed out: the tool answers, but with no session. Its text may hold a token, so
    # the message we raise must not repeat it.
    fake_tool(monkeypatch, json.dumps({"message": "expired", "leak": "a-secret-token"}))
    with pytest.raises(RuntimeError, match="sf org login web") as refused:
        sign_in_with(monkeypatch, SALESFORCE_CLI_ORG="demo-org")
    assert "a-secret-token" not in str(refused.value)


# --- Live mode: one task as it happens (ADR 0032) ------------------------------------------


def test_a_new_handoff_is_sent_once_and_closing_it_completes_it_in_the_crm(simulated):
    from common.store import open_store
    from integrations.crm_sync import complete_task_now, send_task_now

    _, data_dir = simulated
    task = open_store(data_dir).one("SELECT cta_id FROM ctas WHERE status <> 'resolved' LIMIT 1")
    crm = FakeCrm()
    # An older CRM task with the same number, left by an earlier copy of the demo's store
    # (the hosted store is refilled on every deploy and its numbers start again).
    crm.Task.create({"Subject": f"[{task['cta_id']}] an earlier rehearsal", "WhatId": "ACC0000"})
    old = dict(crm.records["Task"])
    first = send_task_now(task["cta_id"], data_dir, client=crm)
    again = send_task_now(task["cta_id"], data_dir, client=crm)  # a second click
    assert first["created"] and not again["created"] and len(crm.records["Task"]) == 2
    assert first["url"].startswith(
        "https://acme-dev-ed.develop.lightning.force.com/lightning/r/Task/"
    )
    (sent,) = [record for key, record in crm.records["Task"].items() if key not in old]
    assert sent["Subject"].startswith(f"[{task['cta_id']}]") and sent["Status"] == "Not Started"

    link = complete_task_now(
        task["cta_id"], "expansion_opportunity", "Call booked.", client=crm, data_dir=data_dir
    )
    assert link and sent["Status"] == "Completed"
    assert "Outcome: expansion opportunity. Call booked." in sent["Description"]
    assert "Status" not in next(iter(old.values()))  # the older task is left alone
    assert complete_task_now("CTA-NOT-THERE", "resolved", client=crm, data_dir=data_dir) is None
    forget_crm_task(data_dir, task["cta_id"])


def test_the_live_link_is_off_unless_asked_for_and_on_the_host_only_for_the_presenter(monkeypatch):
    from integrations.crm_sync import live_enabled

    monkeypatch.delenv("DSO_CRM_LIVE", raising=False)
    monkeypatch.delenv("DSO_HOSTED", raising=False)
    assert not live_enabled() and not live_enabled(presenter=True)
    monkeypatch.setenv("DSO_CRM_LIVE", "true")
    assert live_enabled()
    monkeypatch.setenv("DSO_HOSTED", "1")
    assert not live_enabled()  # a public visitor's handoff never reaches the CRM
    assert live_enabled(presenter=True)


class CountingCrm(FakeCrm):
    """A CRM that also answers how many demo tasks were created today."""

    def __init__(self, created_today: int):
        super().__init__()
        self.created_today = created_today

    def query(self, soql):
        if soql.startswith("SELECT COUNT()"):
            return {"totalSize": self.created_today, "records": []}
        return super().query(soql)


def test_the_hosted_demo_stops_at_its_daily_cap(simulated, monkeypatch):
    import pytest

    from common.store import open_store
    from integrations.crm_sync import send_task_now

    _, data_dir = simulated
    task = open_store(data_dir).one("SELECT cta_id FROM ctas WHERE status <> 'resolved' LIMIT 1")
    monkeypatch.setenv("DSO_HOSTED", "1")
    monkeypatch.setenv("DSO_CRM_DAILY_CAP", "3")  # instead of the 40 a day of the hosted demo
    with pytest.raises(RuntimeError, match="daily limit of 3"):
        send_task_now(task["cta_id"], data_dir, client=CountingCrm(created_today=3))
    assert send_task_now(task["cta_id"], data_dir, client=CountingCrm(created_today=2))["created"]
    forget_crm_task(data_dir, task["cta_id"])
    monkeypatch.delenv("DSO_HOSTED")  # on a laptop there is no cap and no count query
    assert send_task_now(task["cta_id"], data_dir, client=FakeCrm())["created"]
    forget_crm_task(data_dir, task["cta_id"])


def forget_crm_task(data_dir, cta_id):
    """Undo what a send records on the handoff, so the shared test store stays as it was."""
    from common.store import open_store

    store = open_store(data_dir)
    packet = json.loads(
        store.one("SELECT packet FROM ctas WHERE cta_id = :id", id=cta_id)["packet"]
    )
    packet.pop("crm_task_id", None)
    store.update("ctas", {"cta_id": cta_id}, packet=json.dumps(packet))


def test_the_browser_sign_in_wins_over_left_over_passwords(monkeypatch):
    session = {"result": {"instanceUrl": "https://acme.example", "accessToken": "a-session"}}
    fake_tool(monkeypatch, json.dumps(session))
    given = sign_in_with(
        monkeypatch,
        SALESFORCE_CLI_ORG="demo-org",
        SALESFORCE_USERNAME="someone@example.com",
        SALESFORCE_PASSWORD="a password",
        SALESFORCE_SECURITY_TOKEN="a token",
    )
    assert given == {"instance_url": "https://acme.example", "session_id": "a-session"}
