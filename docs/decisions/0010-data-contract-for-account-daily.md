# 0010: One production table per grain, with a contract that is checked by code

Status: accepted (Phase 2). Synthetic data, fictional company.

## Context

Signals, model features, the rules engine, the agents and the dashboards all need the same
facts about an account. If each of them joins raw tables its own way, they will disagree
about what "active users" or "setup complete" means, and nobody will own the difference.

## Options

1. Let each consumer query silver tables directly. Flexible, but definitions drift.
2. One wide gold table, documented in a wiki page. Better, but a wiki page goes stale the
   day someone renames a column.
3. **One wide gold table with a contract kept in the repo and checked on every run.**

## Decision

`gold.account_daily` is the production table: one row per account per day. Its contract,
`contracts/account_daily.yaml`, states the owner, purpose, grain, every column with a type
and a plain-English definition, which columns may be empty, quality rules, freshness, the
consumers, and the change policy.

`contracts/check.py` compares the live table with the contract on every pipeline run:

- no column missing, no column undocumented, types as promised
- required columns have no empty values
- each quality rule returns zero rows
- the source data was loaded within 36 hours

The results are stored in `gold.dq_contract_checks` and a test fails if any promise is
broken. The check is strict in both directions: adding a column without documenting it
fails too.

Change policy: additive changes (a new column) can ship at any time with a contract
update. Breaking changes (remove, rename, retype, redefine) need an ADR and seven days'
notice to the consumers listed in the contract.

## Consequences

- There is one definition of each fact, and one place to look it up.
- Phase 3 adds the health score and the lifecycle stage to the table. That is an additive
  change: new columns, new contract entries, no notice period.
- The table is wide (50 columns). That is deliberate: a consumer reads one row instead of
  writing eight joins.
- Contact facts (who can be emailed) are a current snapshot, so historical rows carry
  today's values for those columns. The contract says so.

## Revisit if

A second grain is needed (for example one row per contact per day). Then it gets its own
table and its own contract; this one is not stretched to cover it.
