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

Signing in (connect, at the bottom of this file) works in three ways, chosen by what is
in .env:

  1. A consumer key and secret (OAuth client credentials). The way the vendor supports
     going forward: no person's password is stored anywhere.
  2. A username, password and security token. Shorter to set up, but orgs created from
     2026 on refuse it until "Enable SOAP API login()" is ticked in the org's Setup.
  3. A sign-in through the browser, held by the vendor's command-line tool. Nothing
     secret is typed or stored in this project at all: .env only names the org.

The steps for each are in docs/decisions/0019.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from api.exports import crm_export
from common.config import load_yaml
from common.paths import DATA_DIR, ROOT
from common.store import open_store

MAX_ACCOUNTS = 50
EXPORT_DIR = ROOT / "exports" / "crm_sync"
PRIORITY = {"urgent": "High", "high": "High", "normal": "Normal", "low": "Low"}
NOTE = "Synthetic data, fictional company (Digital Success OS demo)."
# Who raised a handoff, in words for the CRM task.
SOURCES = {"agent": "the AI agent", "journey": "a play", "mailbox": "the shared mailbox"}


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
    """One open handoff as a CRM task. The id in the subject makes a re-run find it.

    The task's comments are plain text in the CRM (no bold), so each section has a heading
    in capitals, its lines are bullets, a blank line separates the sections, and every code
    is said in words.
    """
    packet = json.loads(task["packet"])
    routing = load_yaml("routing.yaml")
    why = routing["reason_codes"].get(task["reason_code"], task["reason_code"])
    team = routing["queues"].get(task["queue"], {}).get("name", task["queue"])
    raised_by = SOURCES.get(task["source"], task["source"])
    sections = [
        ("NEXT STEP", [packet.get("recommended_next_step") or "See the handoff packet."]),
        ("WHY A PERSON", [why.rstrip(".") + ".", f"For: {team}.", f"Raised by: {raised_by}."]),
    ]
    if packet.get("customer_quote"):
        sections.append(("IN THE CUSTOMER'S WORDS", [f'"{packet["customer_quote"]}"']))
    if packet.get("conversation_summary"):
        sections.append(("WHAT THE AGENT DID", [packet["conversation_summary"]]))
    if packet.get("brief"):
        brief = [line.strip() for line in packet["brief"].splitlines() if line.strip()]
        sections.append(("BRIEF FOR THE SALES TEAM", brief))
    text = "\n\n".join(
        heading + "\n" + "\n".join(f"• {line}" for line in lines) for heading, lines in sections
    )
    if packet.get("draft_reply"):
        # The reply drafted for the person, as an email reads: no bullets. It comes first,
        # so the Sales team can copy it into an email to the admin, check it, and send it.
        contact = packet.get("contact") or {}
        name = contact.get("full_name") or contact.get("name")
        to = f"To: {name}, {contact.get('email')}\n" if contact else ""
        heading = "DRAFT REPLY TO THE CUSTOMER (CHECK, EDIT, SEND)\n"
        text = f"{heading}{to}\n{packet['draft_reply']}\n\n{text}"
    return {
        "Subject": f"[{crm_label(task['cta_id'])}] {task['title']}"[:255],
        "Description": f"{text}\n\n{NOTE}",
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


def crm_label(cta_id: str) -> str:
    """The handoff's name in the CRM: a task there, as a CTA is in the CS platform."""
    return cta_id.replace("CTA-", "TASK-", 1)


def push(
    client, payloads: list[dict], keep_existing: bool = True, created: list | None = None
) -> dict:
    """Send the payloads. `client` is a simple-salesforce connection (or a stand-in).

    Accounts are created once and updated after that. A task is created only if no task
    with its id in the subject exists yet (`keep_existing=False` skips that check). The CRM
    ids of new tasks are added to `created` when a list is given.
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
            marker = task["Subject"].split("]")[0] + "]"  # for example [TASK-00012]
            existing = keep_existing and client.query(
                f"SELECT Id FROM Task WHERE WhatId = '{crm_id}' "
                f"AND Subject LIKE '{marker}%' LIMIT 1"
            )
            if existing and existing["records"]:
                done["tasks_kept"] += 1
            else:
                new = client.Task.create({**task, "WhatId": crm_id})
                done["tasks_created"] += 1
                if created is not None:
                    created.append(new["id"])
    return done


# Three ways to sign in: the browser sign-in first when it is named, then the first
# complete set of credentials found in .env.
OAUTH_SETTINGS = ("SALESFORCE_CONSUMER_KEY", "SALESFORCE_CONSUMER_SECRET", "SALESFORCE_DOMAIN")
PASSWORD_SETTINGS = ("SALESFORCE_USERNAME", "SALESFORCE_PASSWORD", "SALESFORCE_SECURITY_TOKEN")
CLI_SETTING = "SALESFORCE_CLI_ORG"  # the name given to the org at `sf org login web --alias`


def connect():
    """A connection to the CRM, from credentials in the environment (.env). Never in code."""
    from simple_salesforce import Salesforce  # imported here: only a real push needs it

    # The browser sign-in comes first when it is set up: it keeps no secret in .env, and
    # newer orgs refuse the password sign-in anyway.
    if os.environ.get(CLI_SETTING):
        session = cli_session(os.environ[CLI_SETTING])
        return Salesforce(instance_url=session["instanceUrl"], session_id=session["accessToken"])
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
        f"{', '.join(OAUTH_SETTINGS)} or {', '.join(PASSWORD_SETTINGS)} or {CLI_SETTING}. "
        "Steps: docs/decisions/0019. Run without --push for a dry run."
    )


def cli_session(org: str) -> dict:
    """The session the vendor's command-line tool holds for an org, after a browser sign-in.

    `sf org login web --alias <org>` opens the browser, the person approves there, and the
    tool keeps the sign-in in its own store. Here we ask it for the current session. The
    access token is used in this process only: it is never printed and never written into
    the project. (The same idea as the warehouse's browser sign-in.)
    """
    # On Windows the tool installs into the npm folder under APPDATA, which an app's own
    # PATH may lack.
    npm = Path(os.environ.get("APPDATA", "")) / "npm"
    tool = shutil.which("sf") or shutil.which("sf", path=str(npm))
    if tool is None:
        raise RuntimeError(
            f"{CLI_SETTING} is set, but the Salesforce command-line tool (sf) is not installed."
        )

    def ask(*command: str) -> dict:
        answer = subprocess.run(
            [tool, *command, "--target-org", org, "--json"],
            capture_output=True, text=True, check=False,
        )  # fmt: skip
        return json.loads(answer.stdout)["result"]

    try:
        # Two questions: where the org lives, and the current session. (The tool no
        # longer shows the session in `org display`; it has its own command for it.)
        return {
            "instanceUrl": ask("org", "display")["instanceUrl"],
            "accessToken": ask("org", "auth", "show-access-token")["accessToken"],
        }
    except (ValueError, KeyError, TypeError):
        # The tool's output is deliberately not shown: it can contain a token.
        raise RuntimeError(
            f"The command-line tool has no usable sign-in for '{org}'. "
            f"Sign in again with: sf org login web --alias {org}"
        ) from None


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


# --- Live mode: one task at a time, as it happens (ADR 0032) ------------------------------
#
# In the live demo a handoff is sent to the CRM the moment it is created, and closing it in
# the Human console marks it completed there. Switched on by `run.py app --crm` on a laptop,
# or by DSO_CRM_LIVE=true on the host. On the hosted demo only for the presenter, who signs
# in with the admin password, and at most HOSTED_DAILY_CAP new tasks a day: a public
# visitor's handoff never reaches the CRM. A failure is reported on screen and never stops
# the demo.

LIVE_SETTING = "DSO_CRM_LIVE"
CAP_SETTING = "DSO_CRM_DAILY_CAP"
HOSTED_DAILY_CAP = 40


def live_enabled(presenter: bool = False) -> bool:
    """True when a live send is allowed: switched on, and on the host only for the presenter."""
    if os.environ.get(LIVE_SETTING) != "true":
        return False
    return presenter or not os.environ.get("DSO_HOSTED")


def daily_cap() -> int | None:
    """How many new demo tasks the CRM may receive per day. No cap on a laptop."""
    if not os.environ.get("DSO_HOSTED"):
        return None
    return int(os.environ.get(CAP_SETTING) or HOSTED_DAILY_CAP)


def check_daily_cap(client) -> None:
    """Refuse a new task when the hosted demo has already sent its daily share."""
    cap = daily_cap()
    if cap is None:
        return
    sent = client.query(
        "SELECT COUNT() FROM Task WHERE CreatedDate = TODAY AND Subject LIKE '[TASK-%'"
    )["totalSize"]
    if sent >= cap:
        raise RuntimeError(
            f"The demo's daily limit of {cap} tasks in the CRM is reached. "
            "The task is in the Human console as usual."
        )


def send_task_now(cta_id: str, data_dir: Path = DATA_DIR, client=None) -> dict:
    """Send one new handoff to the CRM: its account (created or updated) and the task.

    Returns {"created": bool, "url": link to the task in the CRM}.
    """
    task = open_store(data_dir).one("SELECT * FROM ctas WHERE cta_id = :id", id=cta_id)
    if task is None:
        raise ValueError(f"No task {cta_id}")
    accounts = {row["account_id"]: row for row in crm_export(data_dir)}
    account = accounts.get(task["account_id"])
    if account is None:
        raise ValueError(f"The account of {cta_id} is not in today's data")
    client = client or connect()
    # The handoff remembers the CRM task it created, so a second click sends nothing.
    # Matching on the subject is not enough: the hosted demo's store is refilled on every
    # deploy, task numbers start again, and the CRM may hold an older task with the same id.
    packet = json.loads(task["packet"] or "{}")
    if packet.get("crm_task_id"):
        return {"created": False, "url": task_link(client, packet["crm_task_id"])}
    check_daily_cap(client)
    payload = {"account": account_fields(account), "tasks": [task_fields(task)]}
    created: list = []
    push(client, [payload], keep_existing=False, created=created)
    packet["crm_task_id"] = created[0]
    open_store(data_dir).update("ctas", {"cta_id": cta_id}, packet=json.dumps(packet))
    return {"created": True, "url": task_link(client, created[0])}


def complete_task_now(
    cta_id: str, outcome: str, notes: str = "", client=None, data_dir: Path = DATA_DIR
) -> str | None:
    """Mark the CRM task of a handoff as completed, with the outcome a person recorded.

    Returns a link to the task, or None when the CRM has no task for this handoff.
    """
    client = client or connect()
    task = open_store(data_dir).one("SELECT packet FROM ctas WHERE cta_id = :id", id=cta_id)
    crm_task_id = json.loads((task or {}).get("packet") or "{}").get("crm_task_id")
    if crm_task_id:  # the task this handoff created, not an older one with the same number
        found = client.query(f"SELECT Id, Description FROM Task WHERE Id = '{crm_task_id}'")
    else:
        found = client.query(
            f"SELECT Id, Description FROM Task WHERE Subject LIKE '[{crm_label(cta_id)}]%' "
            "ORDER BY CreatedDate DESC LIMIT 1"
        )
    if not found["records"]:
        return None
    record = found["records"][0]
    closing = f"• Closed in the Human console. Outcome: {outcome.replace('_', ' ')}." + (
        f" {notes}" if notes else ""
    )
    description = record["Description"] or ""
    if closing not in description:  # closing twice must not repeat the line
        description = f"{description}\n\nOUTCOME\n{closing}"
    client.Task.update(record["Id"], {"Status": "Completed", "Description": description[:32000]})
    return task_link(client, record["Id"])


def task_link(client, task_id: str | None) -> str | None:
    """The address of a task in the CRM's own interface."""
    if not task_id:
        return None
    base = getattr(client, "base_url", "") or ""
    host = base.split("/services/")[0] if "/services/" in base else base.rstrip("/")
    host = host.replace(".my.salesforce.com", ".lightning.force.com")
    return f"{host}/lightning/r/Task/{task_id}/view" if host else None
