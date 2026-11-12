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

    def query(self, soql):
        if "FROM Account" in soql:
            number = soql.split("AccountNumber = '")[1].split("'")[0]
            ids = [i for i, r in self.records["Account"].items() if r["AccountNumber"] == number]
        else:
            what = soql.split("WhatId = '")[1].split("'")[0]
            marker = soql.split("LIKE '")[1].split("%")[0]
            ids = [
                i for i, r in self.records["Task"].items()
                if r["WhatId"] == what and r["Subject"].startswith(marker)
            ]  # fmt: skip
        return {"records": [{"Id": i} for i in ids[:1]]}


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
