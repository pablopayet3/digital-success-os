# 0011: Two environments, one codebase, secrets only in the environment

Status: accepted (Phase 3b). Synthetic data, fictional company.

## Context

The demo has to do two things that pull in opposite directions. It must run live in an
interview with no network, no API calls and no chance of a credential failing. And it must
show that the same system would run on real enterprise services.

## Options

1. One environment with feature flags scattered through the code. Quick, but every flag is
   a place where dev and prod can drift apart.
2. Two codebases or branches. Clean separation, double the work, guaranteed drift.
3. **Two named environments, selected by one variable, described in one file.**

## Decision

`DSO_ENV` selects `dev` (default) or `prod`. `config/environments.yaml` says what each one
uses; `common/settings.py` reads it.

| | dev | prod |
|---|---|---|
| Warehouse | local DuckDB file | Databricks SQL warehouse, Unity Catalog `relay` |
| dbt target | `dev` | `prod` (same models, same tests) |
| Operational store | SQLite file | Postgres (URL from `DATABASE_URL`) |
| LLM calls | offline: replay the cache | offline by default; on only with `DSO_OFFLINE_MODE=false` |

Secrets:

- Keys, tokens and passwords are read from environment variables. Locally a `.env` file
  supplies them; in CI and when hosted they come from GitHub Secrets or the host's settings.
- `.env` is git-ignored. `.env.example` lists every variable with no values.
- gitleaks scans for secrets twice: as a pre-commit hook and as a CI job over the whole
  history.
- A missing secret fails with a message that names the variable and says where to put it.
- Secrets are resolved only when used, so `dev` never needs any.

Offline is the default everywhere. Demos, CI and the hosted app never call the paid API.

## Consequences

- Python code that touches the warehouse goes through `common/warehouse.py` and does not
  know which warehouse it is talking to.
- The dbt models must be portable (ADR 0012). A test rejects DuckDB-only SQL in models.
- A reviewer can clone the repo and run everything in `dev` with no accounts at all.

## Revisit if

A third environment is needed (for example a staging workspace). Then add it to
`config/environments.yaml`; nothing else changes.
