"""Push account health and open tasks to the CRM (Salesforce), so sellers see them there.

Synthetic data, fictional company.

Run with:  uv run python run.py crm-sync            dry run: writes what would be sent
           uv run python run.py crm-sync --push     sends it (needs credentials in .env)

Why it exists: a seller lives in the CRM. A health score in a warehouse table helps
nobody until it sits on the account page, and a handoff is only real when it is a task
in the owner's list. This is the "reverse ETL" step, kept deliberately small.

What is sent, using standard objects only (no custom fields to set up in the org):

  Account  matched on AccountNumber (our account id). Name, annual revenue, and a
           Description that carries health, lifecycle, scores, signals and the date.
  Task     one per open handoff, linked to its account. Subject starts with the task id
           in brackets, which is how a second run finds it instead of creating a twin.
           The description carries the next step, the customer's words, what the agent
           did, and the account-owner brief when the task has one.

Safe to run twice: accounts are updated, existing tasks are left alone. Only accounts
that have an open task are sent, at most MAX_ACCOUNTS per run, to stay well inside a
developer org's API limits. Nothing is ever deleted in the CRM.

Signing in (connect, at the bottom of this file) works in two ways, both from .env:

  1. A consumer key and secret (OAuth client credentials). The way the vendor supports
     going forward: no person's password is stored anywhere.
  2. A username, password and security token. Shorter to set up, but orgs created from
     2026 on refuse it until "Enable SOAP API login()" is ticked in the org's Setup.

The steps for each are in docs/decisions/0019.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from api.exports import crm_export
from common.paths import DATA_DIR, ROOT
from common.store import open_store

MAX_ACCOUNTS = 50
EXPORT_DIR = ROOT / "exports" / "crm_sync"
PRIORITY = {"urgent": "High", "high": "High", "normal": "Normal", "low": "Low"}
NOTE = "Synthetic data, fictional company (Digital Success OS demo)."


def build_payloads(data_dir: Path = DATA_DIR, limit: int = MAX_ACCOUNTS) -> list[dict]:
    """What the CRM should hold: one entry per account with an open task, most tasks first."""
    tasks_by_account: dict[str, list[dict]] = {}
    for task in open_store(data_dir).rows("SELECT * FROM ctas WHERE status <> 'resolved'"):
        tasks_by_account.setdefault(task["account_id"], []).append(task)
    accounts = {row["account_id"]: row for row in crm_export(data_dir)}
    busiest = sorted(tasks_by_account, key=lambda a: (-len(tasks_by_account[a]), a))
    return [
        {
            "account": account_fields(accounts[account_id]),
            "tasks": [task_fields(task) for task in tasks_by_account[account_id]],
        }
        for account_id in busiest[:limit]
        if account_id in accounts
    ]


def account_fields(row: dict) -> dict:
    """One account as CRM fields. Everything a seller needs is in the Description."""
    description = (
        f"Health {row['health_score']:.0f} ({row['health_band']}). "
        f"Lifecycle: {row['lifecycle_stage']}. Coverage: {row['coverage_tier']}. "
        f"Churn risk {100 * (row['churn_risk_score'] or 0):.0f}%: "
        f"{row['churn_top_reasons'] or 'nothing stands out'}. "
        f"Expansion likelihood {100 * (row['expansion_score'] or 0):.0f}%: "
        f"{row['expansion_top_reasons'] or 'nothing stands out'}. "
        f"Signals firing: {row['signals_firing'] or 'none'}. "
        f"As of {(row['snapshot_date'] or '')[:10]}. {NOTE}"
    )
    return {
        "AccountNumber": row["account_id"],
        "Name": row["account_name"],
        "Type": "Customer",
        "AnnualRevenue": row["arr"],
        "Description": description,
    }


def task_fields(task: dict) -> dict:
    """One open handoff as a CRM task. The id in the subject makes a re-run find it."""
    packet = json.loads(task["packet"])
    lines = [
        f"Next step: {packet.get('recommended_next_step') or 'see the handoff packet'}",
        f"Why a person: {task['reason_code']} (queue: {task['queue']}, from: {task['source']})",
    ]
    if packet.get("customer_quote"):
        lines.append(f"In the customer's words: {packet['customer_quote']}")
    if packet.get("conversation_summary"):
        lines.append(f"What the agent did: {packet['conversation_summary']}")
    if packet.get("brief"):
        lines += ["Brief for the account owner:", packet["brief"]]
    lines.append(NOTE)
    return {
        "Subject": f"[{task['cta_id']}] {task['title']}"[:255],
        "Description": "\n".join(lines),
        "Priority": PRIORITY.get(task["priority"], "Normal"),
        "Status": "Not Started",
        "ActivityDate": task["sla_due_on"],
    }


def dry_run(data_dir: Path = DATA_DIR, folder: Path = EXPORT_DIR) -> dict:
    """Write exactly what a push would send. Returns the counts."""
    payloads = build_payloads(data_dir)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "payloads.json").write_text(
        json.dumps(payloads, indent=1), encoding="utf-8", newline="\n"
    )
    return {"accounts": len(payloads), "tasks": sum(len(p["tasks"]) for p in payloads)}


def push(client, payloads: list[dict]) -> dict:
    """Send the payloads. `client` is a simple-salesforce connection (or a stand-in).

    Accounts are created once and updated after that. A task is created only if no task
    with its id in the subject exists yet.
    """
    done = {"accounts_created": 0, "accounts_updated": 0, "tasks_created": 0, "tasks_kept": 0}
    for payload in payloads:
        account = payload["account"]
        number = account["AccountNumber"]
        found = client.query(f"SELECT Id FROM Account WHERE AccountNumber = '{number}' LIMIT 1")
        if found["records"]:
            crm_id = found["records"][0]["Id"]
            client.Account.update(crm_id, account)
            done["accounts_updated"] += 1
        else:
            crm_id = client.Account.create(account)["id"]
            done["accounts_created"] += 1
        for task in payload["tasks"]:
            marker = task["Subject"].split("]")[0] + "]"  # for example [CTA-00012]
            existing = client.query(
                f"SELECT Id FROM Task WHERE WhatId = '{crm_id}' "
                f"AND Subject LIKE '{marker}%' LIMIT 1"
            )
            if existing["records"]:
                done["tasks_kept"] += 1
            else:
                client.Task.create({**task, "WhatId": crm_id})
                done["tasks_created"] += 1
    return done


# Two ways to sign in. The first complete set found in .env is used.
OAUTH_SETTINGS = ("SALESFORCE_CONSUMER_KEY", "SALESFORCE_CONSUMER_SECRET", "SALESFORCE_DOMAIN")
PASSWORD_SETTINGS = ("SALESFORCE_USERNAME", "SALESFORCE_PASSWORD", "SALESFORCE_SECURITY_TOKEN")


def connect():
    """A connection to the CRM, from credentials in the environment (.env). Never in code."""
    from simple_salesforce import Salesforce  # imported here: only a real push needs it

    if all(os.environ.get(name) for name in OAUTH_SETTINGS):
        return Salesforce(
            consumer_key=os.environ["SALESFORCE_CONSUMER_KEY"],
            consumer_secret=os.environ["SALESFORCE_CONSUMER_SECRET"],
            domain=my_domain(os.environ["SALESFORCE_DOMAIN"]),
        )
    if all(os.environ.get(name) for name in PASSWORD_SETTINGS):
        return Salesforce(
            username=os.environ["SALESFORCE_USERNAME"],
            password=os.environ["SALESFORCE_PASSWORD"],
            security_token=os.environ["SALESFORCE_SECURITY_TOKEN"],
            domain=my_domain(os.environ.get("SALESFORCE_DOMAIN") or "login"),
        )
    raise RuntimeError(
        "No complete set of CRM credentials in .env. Add either "
        f"{', '.join(OAUTH_SETTINGS)} or {', '.join(PASSWORD_SETTINGS)}. "
        "Steps: docs/decisions/0019. Run without --push for a dry run."
    )


def my_domain(value: str) -> str:
    """The part of the org's address the sign-in needs, whatever form was pasted.

    "https://acme-dev-ed.develop.my.salesforce.com/" and
    "acme-dev-ed.develop.lightning.force.com" both become "acme-dev-ed.develop.my".
    """
    host = value.strip().removeprefix("https://").removeprefix("http://").split("/")[0]
    host = host.replace(".lightning.force.com", ".my.salesforce.com")
    return host.removesuffix(".salesforce.com")


def explain_refusal(error: Exception) -> str:
    """What to do when the CRM refuses the sign-in, in plain words."""
    lines = [
        f"The CRM refused the sign-in: {error}",
        "Nothing was sent. Things to check, in this order:",
        "  1. With a username and password: a new org blocks this way of signing in. In the",
        '     org\'s Setup, search for "User Interface" and tick "Enable SOAP API login()".',
        '  2. The security token is the one from the latest "Reset My Security Token" email.',
        "  3. With a consumer key and secret: SALESFORCE_DOMAIN is the org's own address",
        "     (My Domain), and a new app can take ten minutes to start working.",
        "Steps for both ways: docs/decisions/0019.",
    ]
    return "\n".join(lines)
