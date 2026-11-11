# Digital Success OS (mini)

> Synthetic data, fictional company. "Lumen Labs" and its product "Relay" do not exist.

## What this is

A portfolio demo for a hiring-manager interview. It turns raw customer signals into plays,
AI-agent actions and human handoffs, with a return signal, measured against a holdout.
The full brief is in `BRIEF.md` (kept out of git).

Story in one line: telemetry and CRM data land in a pipeline, become clean tables with
data-quality tests, become signals and model scores, trigger plays (journey, AI agent or a
task for a human); when the agent cannot help it hands off with full context, and the
human's outcome comes back into the system. Every play has a holdout.

## The fictional world

- Company: Lumen Labs. Product: Relay (Relay Boards, Relay Docs, Relay Assist).
- Editions: free, standard, premium, enterprise.
- Coverage tiers: `high_touch`, `pooled`, `uncovered`. The pilot runs on `uncovered`.

## Conventions

- **Never use real company names, logos or branding** in data, code or screens. The only
  place real tool names appear is the tool-mapping table in the README.
- Every file and screen says "Synthetic data, fictional company".
- Simple, readable code over clever code. The owner is not a software engineer and will
  walk through this code live. Short functions, plain names, comments that say why.
- Every design decision gets an ADR in `docs/decisions/` (context, options, decision,
  consequences, revisit if).
- Tests as we go: pytest for Python, dbt tests for data.
- Commit after every phase. Each phase leaves the project runnable.
- Core before Stretch in every phase.
- Keep LLM costs low: cache responses, small batches, and an offline mode that replays
  the cache.
- Ground truth (`data/ground_truth/`) is an answer key. The pipeline, the models and the
  agents never read it. Only validation and evaluation code may.

## How to run

```
uv sync
uv run python run.py data      # generate the synthetic world (about 25 seconds)
uv run python run.py pipeline  # ingest + dbt build + freshness + contract check
uv run python run.py test
uv run python run.py lint
```

`run.py` is the entry point (there is no `make` on the Windows machine this was built on).
The `Makefile` only forwards to it.

Windows note: keep the repo in a short path. In a deeply nested folder, file paths inside
`.venv` and `dbt/target` exceed 260 characters and imports fail. If that happens, set
`UV_PROJECT_ENVIRONMENT`, `DBT_TARGET_PATH` and `DBT_LOG_PATH` to short folders.

"Today" in the warehouse is the latest licence snapshot date (dbt macro `as_of_date()`),
never the real clock. The data runs on a simulated calendar.

## Decisions that differ from the brief

| Brief | What we do | ADR |
|---|---|---|
| Makefile entry point | `run.py`, with the Makefile as a thin wrapper | 0006 |
| Generate 120 days up front, add treatment effects to outcomes afterwards | A day-by-day world (`World.step`) that reacts to touches from Phase 4 | 0005 |
| 120 days, labels from hidden ground truth | 180 days; labels from churn and expansion recorded in the CRM files | 0007 |
| About 600 accounts | 1,200 (1,091 signed up by the end of history) | 0007 |
| Seven sources | Plus `crm_opportunities.csv`, `email_engagement.csv`, and `product_user_id` on contacts | 0007 |
| (not stated) | No LLM in the generator: templates plus noise | 0008 |

Flagged for later phases: operational state in SQLite rather than the DuckDB file
(Phase 4), JSON traces only (Phase 5), 50% holdout and leading-indicator metrics for the
pilot (Phase 6).

## Brief update (v1.1 + v1.2 + cost rules), received during Phase 3

Full text is appended to `BRIEF.md`. Rules: do not redo finished work, finish the current
phase first, then fold the changes into the remaining phases.

**Part A (v1.1)**: every item was already in the brief. Intervention ladder and rollout
stage (Phase 4), lifecycle rules in `docs/metrics.md` (Phase 3), data requirements, play
specs, pilot plan and change control (Phases 5 and 8), Pilot page (Phase 7), README
real-job mapping and demo script (Phase 8).

**Part B (v1.2): production profile.** Two environments, same code and same dbt models:
`dev` = local DuckDB + offline mode; `prod` = real services. Selected with `DSO_ENV`.

| # | Item | Where it lands |
|---|---|---|
| 8 | Environments, secrets from env vars, gitleaks in pre-commit and CI | Phase 3b |
| 9 | Dockerfile (app + API), docker-compose | Phase 9 (after the app exists) |
| 10 | GitHub Actions: ruff, pytest, dbt build on PR; build and deploy on merge | CI in Phase 3b, deploy in Phase 9 |
| 11 | Databricks Free Edition as prod warehouse: dbt `prod` target, `relay.bronze/silver/gold`, landing files in a volume, portable SQL | Portable SQL and target in Phase 3b; live run when credentials exist |
| 12 | Daily scheduled pipeline as a GitHub Actions cron, failure alerts | Phase 9 |
| 13 | Hosted app and API (Render or Streamlit Community Cloud, never Railway), offline mode, login with roles CSM / Sales / Admin on the Human console | Login in Phase 7, deploy in Phase 9 |
| 14 | Structured JSON logs, LangSmith traces with PII masking, `/health` | Phases 5 and 7 |
| 15 | `docs/production-architecture.md` with real-vs-simulated table | Phase 8 |
| 16 | Postgres operational store (if time) | Phase 4 builds the store on SQLAlchemy: SQLite in dev, Postgres in prod by URL |
| 17 | Salesforce Developer Edition sync (if time) | After Phase 9 |
| 18 | Tableau Public dashboard (if time) | After Phase 9: extracts and build guide |
| 19 | Gainsight-shaped export (if time) | Phase 7, with the CRM export |

**Part C: cost rules.** Free tiers only. The Claude API is the only paid service: a small
model for classification, simulation and the judge, a stronger one only for the agent's
customer-facing replies; model names in config; every response cached;
`MAX_LLM_CALLS_PER_RUN` and `LLM_BUDGET_USD` stop a run cleanly and log the spend; at most
50 simulated agent conversations per run; offline mode is the default (demos, CI and the
hosted app never call the API).

**Part D.** After each phase: what works, how to run it, the three design decisions to
defend, commit. All names stay fictional; "Synthetic data" banner on every page.

**SQL portability rule (from Phase 3b on):** no DuckDB-only functions in dbt models. Use
dbt cross-database macros and the project's own dispatch macros in `dbt/macros/`.

## Phases

1. Skeleton and synthetic data: **done**
2. Pipeline and data quality (ingest, dbt bronze/silver/gold, tests, contract): **done**
3. Signals, health score, segmentation, churn and expansion models: **done**
3b. Environments, secrets, CI, Databricks `prod` target, portable SQL: **next**
4. Rules engine, journeys, consent, holdout assignment
5. Agents and human fallback
6. Evals and experiments
7. App and API
8. Docs, demo, portfolio

What works after each phase, and what to be able to explain, is in `docs/phase-notes.md`.

## Map of the code so far

- `run.py`: task runner.
- `config/world.yaml`: generator settings. `config/rollout.yaml`: pilot segments, offline mode.
- `common/`: paths and config loading.
- `synth/world.py`: the `World` class; `step()` simulates one day.
- `synth/accounts.py`: accounts, contacts and their hidden traits.
- `synth/behavior.py`: product usage, setup, expansion, churn. All the behavioural assumptions.
- `synth/interactions.py`: tickets, NPS, emails and mailbox replies.
- `synth/text.py`: wording templates. `synth/mess.py`: deliberate data problems.
- `synth/generate.py`: writes `data/landing/` and `data/ground_truth/`.
- `synth/report.py`: the generation report.
- `ingest/schemas.py`: the pydantic `ProductEvent` and `validate_event` (reason codes).
- `ingest/load.py`: bronze loads, dead letter, load log. `ingest/transform.py`: runs dbt,
  stores test and freshness results. `ingest/pipeline.py`: the whole pipeline in one call.
- `dbt/models/staging/`: silver (`stg_*`). `dbt/models/marts/`: gold. `account_daily` is
  the production table; `int_account_daily_base` holds the joins.
- `dbt/seeds/edition_limits.csv`: edition limits (must match `config/world.yaml`; tested).
- `contracts/account_daily.yaml` and `contracts/check.py`: the data contract and its checker.
- `config/health.yaml` (weights, bands) and `config/models.yaml` (snapshots, capacity).
- `analytics/features.py`: model features and their plain-word phrases.
  `analytics/train.py`: trains churn, expansion and clusters, writes metrics and cards.
  `analytics/score.py`: scores all account-days, flags by capacity, writes reasons.
  `analytics/eda.py`: writes `docs/eda-report.md`.
- dbt marts added in Phase 3: `int_account_daily_health`, `fct_outcome_labels`,
  `account_daily` (now with scores and lifecycle), `signals`, `account_current`.
  Models tagged `scored` are built in a second dbt stage, after `analytics/score.py`.
- `tests/conftest.py`: one small world, one pipeline run and one training run shared by
  all tests. Tests never touch the real `analytics/models/` or `docs/model-cards/`.
- `tests/test_synth.py` (Phase 1), `tests/test_pipeline.py` (Phase 2),
  `tests/test_models.py` (Phase 3).

Pipeline order: ingest -> dbt (exclude tag:scored) -> score -> dbt (select tag:scored) ->
freshness -> contract check. dbt is always run through `run.py` / `ingest/transform.py`,
which passes the health weights as dbt vars.

Warehouse schemas: `bronze` (raw, loaded by ingest), `silver` (dbt staging), `gold` (dbt
marts, plus `dq_test_results`, `dq_freshness`, `dq_contract_checks` written by Python).
