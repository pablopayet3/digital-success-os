# 0012: Databricks Free Edition as the prod warehouse, with portable SQL

Status: accepted (Phase 3b) and **run against a real Free Edition workspace**: see "The
first real run" at the end.
Synthetic data, fictional company.

## Context

In the real role the warehouse is a cloud lakehouse. The demo should prove that the same
models run there, without paying for anything. Databricks Free Edition gives a real
workspace with Unity Catalog and a SQL warehouse, at no cost, with limits.

Free Edition limits that shape this design:

- **One 2X-Small SQL warehouse.** Enough for this data (about 500,000 events), slow for
  anything much larger. No autoscaling.
- **Fair-use daily quotas.** A run that exceeds them is stopped until the next day. So the
  scheduled pipeline runs once a day and rebuilds only what it needs.
- **Restricted outbound internet.** Code running inside Databricks cannot call external
  APIs freely. So LLM calls and model scoring run outside (in the app or the CI runner)
  and only read from and write to the warehouse.
- **Non-commercial use only.** Fine for a portfolio demo. Not a path to production.

## Options

1. Keep DuckDB only and describe the cloud version in a document. No proof.
2. Maintain a second set of SQL models for Databricks. Proof, but two things to keep in step.
3. **One set of models that runs on both, with the differences isolated in macros.**

## Decision

Option 3.

- dbt has two targets in `dbt/profiles.yml`: `dev` (DuckDB) and `prod` (dbt-databricks,
  catalog `relay`, schemas `bronze`, `silver`, `gold`).
- **Portable SQL.** Model files use no database-specific functions. Differences live in
  `dbt/macros/portable.sql` (days before and after a date, days between dates, text casts,
  JSON field access, sorted text lists) and in dbt's own cross-database macros. A test
  (`tests/test_environments.py`) scans the models for DuckDB-only syntax and fails on any.
  The one construct that had to be rewritten was DuckDB's `ASOF JOIN` for "latest NPS
  answer before each day"; it is now a `row_number()` window, which runs everywhere.
- **Landing zone.** In prod, landing files are uploaded to a Unity Catalog volume
  (`/Volumes/relay/bronze/landing`) and bronze tables are created from them with
  `read_files()` (`ingest/load_databricks.py`). Events are validated first, with the same
  pydantic check as in dev; rejected rows go to `relay.bronze.dead_letter`.
- **Python stays outside.** Scoring reads features from the warehouse and writes scores
  back through `common/warehouse.py`. The model never runs inside Databricks.
- Bronze is rebuilt from the volume on each run. At scale this becomes an incremental load
  (Auto Loader or COPY INTO).

## Consequences

- One model per table, tested on DuckDB on every pull request. The same tests run on
  Databricks with `--target prod`.
- dbt-databricks currently requires an older dbt-core (1.10) than dbt-duckdb alone would
  use. It works, with a deprecation notice. Upgrade when the adapter allows it.
- Until credentials exist, "passes on both targets" is proven for DuckDB only. The first
  prod run will likely need small fixes (type names, `read_files` options).
- The exploratory analysis script (`analytics/eda.py`) is a dev tool and uses DuckDB-only
  SQL on purpose.

## The first real run

The whole pipeline ran against a Databricks Free Edition workspace with `DSO_ENV=prod`:
landing files uploaded to a Unity Catalog volume, bronze tables created from them, the
same dbt models built in `relay.silver` and `relay.gold`, scores written back, freshness
and the contract checked.

| | Result |
|---|---|
| dbt models and data tests | 100 of 100 tests pass, first time, with no change to any model |
| Data contract on `gold.account_daily` | 14 of 14 checks pass |
| Tables created | 23 bronze, 15 silver, 21 gold |
| Agreement with DuckDB | 10 of 11 checks identical (row counts, events kept and rejected, ARR, red accounts, signals, churn flags, experiment outcomes). The eleventh, an average health score, differs in the third decimal (68.551 against 68.552): rounding |

What that shows: the portable-SQL rule did its job. Every model was written and tested
only on DuckDB, and all of them ran unchanged on Databricks.

What broke, and it was Python, not SQL:

- **A column Databricks adds.** `read_files()` adds a `_rescued_data` column. The table
  writer used it to load Parquet, the column came back on the next read, and the next
  write failed. The writer now reads the Parquet file directly and drops a stray column.

Two things worked that the ADR had left open:

- **Creating a catalog** is allowed on Free Edition. The code creates `relay` on first
  run, and `DATABRICKS_CATALOG` points it at an existing one where that is not allowed.
- **No access token.** Locally the project signs in through the browser (OAuth) and
  keeps the short-lived token in memory. A personal access token is needed only where
  there is no browser, as a secret in CI.

Still not done: the operational store used SQLite for this run (`DATABASE_URL` pointed
at the local file). Postgres has not been run.

## Revisit if

The data outgrows a 2X-Small warehouse or the daily quota, or the organisation already has
a paid workspace. Then point the `prod` target at it; the models do not change.
