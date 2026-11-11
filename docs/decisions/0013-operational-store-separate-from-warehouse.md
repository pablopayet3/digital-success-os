# 0013: Live state in an operational store, analysis in the warehouse

Status: accepted (Phase 4). Covers brief update item 16. Synthetic data, fictional company.

## Context

The engine needs to remember things that change one row at a time: who is enrolled in
which play, which step they are on, which tasks are waiting for a human, who opted out
an hour ago. The warehouse is the wrong place for that:

- DuckDB lets only one process write at a time. The app, the API and the daily run all
  need to write. A lock error during the live demo is a real risk.
- A Databricks SQL warehouse is built for large reads, not for updating one row when a
  human clicks "resolve".
- In the real company these are different systems anyway: the lakehouse for analysis, the
  CS platform for operations.

## Options

1. Keep everything in the warehouse. One system, but the wrong tool for single-row
   updates, and unsafe with several writers.
2. **A separate transactional store (OLTP), copied into the warehouse (OLAP) daily.**

## Decision

Option 2. `common/store.py` is the operational store, written with SQLAlchemy so the same
code runs on:

- **SQLite** in dev (`data/ops.db`): no setup, safe with several processes.
- **Postgres** in prod (`DATABASE_URL`, for example Neon or Supabase free tier).

It holds enrolments, the audit log, touches, journey events, CTAs with their handoff
packets, consent changes, paused accounts, queue alerts and the evaluation review queue.
Dates are stored as ISO text and JSON as text, so both databases behave identically.

Every pipeline run copies these tables as they are into the warehouse
(`bronze.ops_*`, in `ingest/load_ops.py`). Metrics and experiments are then computed in
dbt like everything else.

The engine reads facts from gold and writes decisions to the store. It never writes to
gold, and the warehouse never writes to the store.

## Consequences

- The Human console and the API can resolve a CTA while the pipeline is running.
- Operational data reaches the dashboards with up to a day's delay. That is normal for a
  daily batch and is stated on the dashboards.
- An opt-out learned by the system (an "unsubscribe" reply) is honoured at once: the
  engine checks the store's consent changes as well as the CRM snapshot.
- Two stores can drift. The world and the store are saved after every simulated day, and
  the store is rebuilt whenever the world is regenerated.
- Postgres has been written for but not yet run against (needs a `DATABASE_URL`).

## Revisit if

The organisation's CS platform becomes the system of record for CTAs. Then this store
shrinks to the engine's own bookkeeping and CTAs are created through that platform's API.
