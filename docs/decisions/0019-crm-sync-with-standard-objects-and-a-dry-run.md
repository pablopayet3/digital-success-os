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
