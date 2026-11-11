# 0001: DuckDB and dbt for the warehouse, uv and Python 3.12 for the environment

Status: accepted (Phase 1). Synthetic data, fictional company.

## Context

The demo needs a warehouse with bronze, silver and gold layers, SQL transformations, tests
and documentation. It must run on one laptop, with no cloud account, and must not fail
during a live demo. In the real role this work sits in a cloud lakehouse.

## Options

1. **DuckDB + dbt-core.** A local, single-file analytical database, with the same
   transformation tool many data teams use in production.
2. SQLite + hand-written SQL scripts. Simpler, but no tests, no lineage, weak analytics.
3. A cloud warehouse trial. Closest to the real thing, but needs an account, a network
   connection and credentials during the demo.

## Decision

DuckDB as the warehouse, dbt-core with dbt-duckdb for transformations, tests, freshness and
docs. The environment is managed with uv, Python is pinned to 3.12, and the lockfile is
committed.

## Consequences

- Zero infrastructure. `uv sync` and one command rebuild everything.
- The SQL patterns (medallion layers, incremental loads, tests, contracts) carry over
  directly to a cloud lakehouse.
- DuckDB allows one writing process at a time. That shapes where operational state lives
  (decided in Phase 4).
- Python 3.12 rather than the newest version, because the data libraries support it best.

## Revisit if

Data no longer fits on one machine, or several processes need to write at the same time.
