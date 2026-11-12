# 0019: CRM sync with standard objects, idempotent, dry run by default

Status: accepted. Synthetic data, fictional company. This record names a real CRM
product because the sync is written for it.

## Context

Scores and handoffs are only useful where people work. A seller lives in the CRM: a
health score in a warehouse table does nothing for them, and a handoff is only real when
it is a task in their list. The demo already exposes CRM-shaped exports through the API.
What was missing is the step that actually writes into a CRM.

## Options

1. Custom fields on the account (health score, churn risk, signals as separate fields).
   The right shape for reporting, but every org needs those fields created first, and a
   demo that starts with a metadata deployment is fragile.
2. **Standard objects only.** The account's Description carries the health summary; each
   open handoff becomes a standard Task linked to the account.
3. A reverse-ETL product. The right answer at scale; a paid dependency here.

## Decision

Option 2, in `integrations/crm_sync.py`, with three rules.

- **Dry run by default.** `run.py crm-sync` writes exactly what would be sent to
  `exports/crm_sync/payloads.json`. Sending needs `--push` and credentials in `.env`.
- **Safe to run twice.** Accounts are matched on AccountNumber (our account id) and
  updated. A task's subject starts with its id in brackets; a task that already exists is
  left alone. Nothing is ever deleted in the CRM.
- **Small on purpose.** Only accounts with an open task, at most 50 per run, so a free
  developer org's API limits are never a concern.

A task for Sales carries the account-owner brief in its description, so the seller reads
the evidence where they work, not through a link back to this system.

## Signing in: two ways, because the vendor is closing one

The first version signed in with a username, a password and a security token. That
uses an older sign-in call which the vendor is retiring: orgs created from early 2026 on
refuse it by default, and it stops for everyone in mid 2027. So `connect()` accepts
either set of settings from `.env` and uses the first complete one:

| Way | Settings in `.env` | When to use it |
|---|---|---|
| A consumer key and secret (OAuth client credentials) | `SALESFORCE_CONSUMER_KEY`, `SALESFORCE_CONSUMER_SECRET`, `SALESFORCE_DOMAIN` | The supported way. No person's password is stored |
| A username, password and security token | `SALESFORCE_USERNAME`, `SALESFORCE_PASSWORD`, `SALESFORCE_SECURITY_TOKEN` | Quickest on a demo org, once the old sign-in is allowed |
| A sign-in through the browser, held by the vendor's command-line tool | `SALESFORCE_CLI_ORG` (a name for the org, not a secret) | On a person's own machine. Nothing secret is typed or stored in the project |

A refused sign-in prints what to check, in plain words, and sends nothing.

### Steps: sign in through the browser (the least to type)

1. Install the vendor's command-line tool once: `npm install --global @salesforce/cli`.
2. `sf org login web --instance-url <the org's address> --alias dso-demo`. The browser
   opens; approve the request there. The tool keeps the sign-in in its own store.
3. Put `SALESFORCE_CLI_ORG=dso-demo` in `.env`.
4. `uv run python run.py crm-sync --push`. The sync asks the tool for the current
   session and uses it in memory only: it is never printed or written to a file.

This is the same design as the warehouse's browser sign-in (ADR 0012). It suits a
person at a laptop; a scheduled job needs the consumer key instead.

### Steps: username, password and security token (about five minutes)

1. Create a Developer Edition org at developer.salesforce.com/signup. Confirm the email
   and set a password.
2. In the org: gear icon, Setup. In Quick Find type "User Interface", open it, tick
   "Enable SOAP API login()", save. A new org refuses the sign-in without this.
3. Your picture (top right), Settings, "Reset My Security Token". It arrives by email.
4. Fill the three `SALESFORCE_USERNAME`, `_PASSWORD` and `_SECURITY_TOKEN` lines in `.env`.
5. `uv run python run.py crm-sync --push`.

### Steps: consumer key and secret

1. Setup, Quick Find "External Client App Manager", New External Client App. Give it a
   name and a contact email.
2. Enable OAuth. Callback URL: `https://localhost/callback` (this flow never calls it,
   but the form requires one). Scope: "Manage user data via APIs (api)". Tick "Enable
   Client Credentials Flow". Create.
3. On the app's Policies tab: edit, enable the client credentials flow, and enter your
   own username under "Run As". Save.
4. On the Settings tab, under OAuth settings, open "Consumer Key and Secret" (a code is
   emailed to confirm it is you).
5. Setup, Quick Find "My Domain": copy the org's own address.
6. Fill `SALESFORCE_CONSUMER_KEY`, `SALESFORCE_CONSUMER_SECRET` and `SALESFORCE_DOMAIN`
   (the address from step 5, in any form) in `.env`. A new app can take ten minutes to
   start working.

The screen labels are the vendor's as of late 2026 and move between releases.

## Consequences

- It works on any org with no setup, and a seller can read it without training.
- A Description is text, not data: it cannot be filtered or reported on. Custom fields
  are the next step once the org is the company's own.
- Tests use a stand-in CRM and check the mapping and the run-twice rule
  (`tests/test_crm_sync.py`).

## Not yet verified

The live push has not been run: it needs a Salesforce Developer Edition org and its
credentials. The dry run and the tests are what has been verified.

## Revisit if

The CRM becomes the system people report from (move to custom fields), or volumes pass a
few thousand records a day (use the bulk API or a reverse-ETL tool).
