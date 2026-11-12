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

## Verified on a real Postgres

A CI job (`store-on-postgres` in `.github/workflows/ci.yml`) starts a Postgres 16
service on every push and does two things:

- runs the store tests (`tests/test_store.py`) on SQLite and on Postgres: the same
  seven tests on each, so the two cannot drift apart;
- runs the engine for three simulated days with its live state in Postgres (DuckDB
  stays the warehouse), then checks the rows are really there. On the first run: 107
  enrolments, 224 audit decisions, 59 tasks and 62 triaged replies, in Postgres.

It passed first time. Storing dates as ISO text and JSON as text is what made that
uneventful: the two databases never had to agree on a date or JSON type. One change
was needed beforehand: the store now keeps one database engine per URL for the whole
process. Opening a new one on every call was harmless on SQLite and would have leaked
connections on Postgres.

**Hosted, too.** The host's blueprint (`render.yaml`) creates a free Postgres database
and passes its address to the app and the API, so both share one operational store and
nobody types a connection string. When a service starts it copies the demo state into
the hosted store once (`scripts/seed_store.py`), under a database lock because two
services start together; if the database cannot be reached, the service falls back to
its local file and still comes up. CI proves the seeding on a real Postgres (649 rows
copied the first time, nothing touched the second), and the hosted API's `/health`
reports `operational_store: ok (postgresql)`. A free hosted database expires after a
period set by the host; the fallback covers that.

## Revisit if

The organisation's CS platform becomes the system of record for CTAs. Then this store
shrinks to the engine's own bookkeeping and CTAs are created through that platform's API.
