# Digital Success OS (mini)

> Synthetic data, fictional company. "Lumen Labs" and its product "Relay" do not exist.

## What this is

A portfolio demo. It turns raw customer signals into plays,
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

- **Never use real company names, logos or branding** in data, code or screens. Real tool
  names appear only in the README mapping tables, `docs/production-architecture.md`,
  `docs/demo-script.md`, `docs/bi-dashboard-guide.md`, `integrations/crm_sync.py` with
  ADR 0019, the ADRs about the production profile (the brief update asked for those),
  and `config/tour.yaml`: the app's guided tour names them as plain text, with no
  logos, because the owner asked for it on 12 November 2026. No other screen does. The app does not list those two documents. The employer is never named.
- Every file and screen says "Synthetic data, fictional company".
- Simple, readable code over clever code. This code is walked through live, line by line.
  Short functions, plain names, comments that say why.
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
3b. Environments, secrets, CI, Databricks `prod` target, portable SQL: **done** (CI runs
    on GitHub Actions; the prod pipeline has run on Databricks)
4. Rules engine, journeys, consent, holdouts, daily loop: **done**
5. Agents and human fallback, with LLM cost controls: **done** (live run done; the real
   responses are cached in `cache/llm/` and replayed by default)
6. Evals and experiments: **done** (eval report from the real model, replayable from the cache)
7. App and API: **done**
8. Docs, demo, portfolio: **done** (README, operating documents, demo script, portfolio entry)
9. Container, deploy and daily workflows: **done and passing on GitHub Actions**
   (github.com/pablopayet3/digital-success-os, public). Hosted on Render from the blueprint

Still not run against the real thing (needs a key only the owner can supply): trace
export to a tracing service.

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

Phase 3b and 4 additions:

- `common/settings.py` (DSO_ENV, secrets), `common/warehouse.py` (DuckDB or Databricks),
  `common/store.py` (operational store: SQLite or Postgres via SQLAlchemy).
- `config/plays.yaml`, `config/journeys.yaml`, `config/routing.yaml`: the play catalog.
  `config/sim_effects.yaml`: simulator assumptions (never read by engine, models, agents).
- `engine/catalog.py` (load and validate config), `engine/assignment.py` (hash holdout and
  rollout), `engine/context.py` (the day's data), `engine/consent.py`, `engine/rules.py`,
  `engine/journeys.py`, `engine/channels.py`, `engine/handoff.py` (packet, create, resolve,
  capacity), `engine/humans.py` (simulated staff), `engine/run.py` (run-day, run-days),
  `engine/templates/` (email and in-app templates).
- `agents/briefs.py`: template account-owner brief (Phase 5 adds the LLM version).
- `synth/reactions.py`: how simulated customers react to touches.
- `ingest/load_ops.py`: copies the operational store into `bronze.ops_*`.
- `ingest/load_databricks.py`: prod loader (run for real; see ADR 0012).
- Tests: `test_environments.py`, `test_engine.py`. The test session simulates six days.

A simulated day: world steps (reacting to yesterday's touches) -> pipeline (checks=False)
-> staff work queues -> rules engine -> journey runner -> capacity check. The world is
saved after every day. Regenerating data deletes the warehouse and the operational store.

Pipeline order: ingest (+ copy ops store) -> dbt (exclude tag:scored) -> score -> dbt
(select tag:scored) -> freshness -> contract check. dbt is always run through `run.py` / `ingest/transform.py`,
which passes the health weights as dbt vars.

Warehouse schemas: `bronze` (raw, loaded by ingest), `silver` (dbt staging), `gold` (dbt
marts, plus `dq_test_results`, `dq_freshness`, `dq_contract_checks` written by Python).

Phase 5 additions:

- `config/llm.yaml` (model per job, prompt version, prices), `config/play_specs.yaml`
  (the wording of play specs). `llm_stand_in` in `config/environments.yaml`.
- `agents/llm.py` (the only caller of the LLM API: cache, offline, limits),
  `agents/stand_in.py` (rule-based stand-in, labelled, used when `llm_stand_in` is true
  and by the tests), `agents/retrieval.py` (BM25 over `kb/`), `agents/escalation.py`
  (hard rules), `agents/tools.py`, `agents/onboarding.py` (`converse()`; no side effects),
  `agents/runner.py` (journey agent step, handoff, stores conversations and traces),
  `agents/simulated_customer.py`, `agents/classify.py`, `agents/mailbox.py` (triage and
  routing), `agents/feedback.py` (NPS and ticket themes), `agents/briefs.py`,
  `agents/tracing.py` (masked JSON traces in `data/traces/`).
- `prompts/` (versioned agent prompts with a changelog, classifier prompts), `kb/` (23
  fictional help articles).
- `engine/specs.py` writes `docs/play-specs/<play_id>.md` from the config
  (`run.py specs`); a test fails when they are out of date.
- LLM modes: offline replay of `cache/llm/` (the default: real responses, committed),
  stand-in (`--stand-in`; CI, the daily workflow and the container image), live
  (`--live`: `DSO_OFFLINE_MODE=false` and `DSO_LLM_STAND_IN=false` with
  `ANTHROPIC_API_KEY`).
- A simulated day is now: world -> pipeline -> staff -> mailbox triage -> feedback
  classification -> rules -> journeys (agent steps) -> capacity check.
- Tests: `tests/test_agents.py`, `tests/fake_llm.py`.

Phases 6 to 9 additions:

- dbt: `stg_ops_*` (operational tables), `metrics_play_outcomes` (one row per enrolment,
  six yes/no outcomes), `metrics_play_summary`, `metrics_play_ladder`, `metrics_handoffs`,
  `metrics_agent`. All tagged `scored`. The measurement window is passed as a dbt var.
- `experiments/analyze.py` (`run.py experiments`): z-test, interval, split check
  (alarm below 0.001, "uneven" below 0.01), smallest detectable lift, cohorts, ladder,
  revenue, verdict and recommendation. Writes `gold.experiment_results` and
  `experiments/reports/`.
- `evals/` (`run.py evals`): cases in `evals/cases/*.yaml` (accounts, onboarding agent,
  mailbox, briefs), `evals/run.py`, reports in `evals/reports/`. `prompts/judge.md`.
  Cases marked `needs_model` are skipped for the stand-in.
- `api/main.py` and `api/exports.py` (`run.py api`). `common/logs.py` (JSON logs),
  `common/today.py` (the warehouse's "today").
- `app/main.py`, `app/ui.py`, `app/views/*.py` (`run.py app`). Console passwords:
  `CONSOLE_PASSWORD_CSM/SALES/ADMIN`; locally `demo` when unset; none when `DSO_HOSTED` is set.
- `run.py demo [days] [--profile small]` builds everything from nothing.
- `Dockerfile`, `docker-compose.yml`, `render.yaml`, `.github/workflows/deploy.yml`,
  `.github/workflows/daily.yml`, `.github/pull_request_template.md`.
- Docs: `prd`, `roadmap`, `principles`, `ownership-map`, `change-control`,
  `data-requirements`, `pilot-plan`, `dependency-map`, `production-architecture`,
  `demo-script`, `portfolio-entry`. ADRs 0016 to 0018.
- Tests: `tests/test_evals.py`, `tests/test_api.py`.
- `DSO_DATA_DIR` points the app and the API at another data folder (tests, containers).

The live run is done: `cache/llm/` holds the real model responses (committed), replay
is the default mode, the agent prompt in use is v3, and every stored conversation
records who answered (`answered_by`). `run.py` takes `--live` and `--stand-in`.
`run.py review` writes `docs/operating-review.md`; `run.py extracts` writes
`exports/bi/` (guide: `docs/bi-dashboard-guide.md`, which names a real BI product).
Stand-in eval runs write to `evals/reports/stand-in/`, never over the real report.

CRM sync: `integrations/crm_sync.py` (`run.py crm-sync`, dry run by default, `--push`
to send; standard Account and Task objects; safe to run twice; ADR 0019). The live push
has run against a Developer Edition org (6 accounts, 6 tasks; a second run created
nothing), signed in through the browser with the vendor's command-line tool:
`SALESFORCE_CLI_ORG=dso-demo` in `.env`, and `sf` must be on the PATH (it installs to
`%APPDATA%\npm`, which this app's shell does not have on its PATH by default).
200 tests in total.

After the phases (the brief read again line by line; see the last section of
`docs/phase-notes.md`):

- `engine/pilot.py`: the readiness checklist answered from live data, and the weekly
  review notes. Bars in `config/rollout.yaml` (`readiness`). ADR 0020.
- `engine/journeys.py::journey_funnel`: the funnel per journey, from `journey_events`.
- `engine/rules.py::preview_segment`: what adding a coverage tier would do today, by the
  engine's own rules, writing nothing. Shown on the Pilot page with a capacity check.
- `gold.metrics_handoffs` has `recontacted`, `picked_up` and `days_to_pickup_total`;
  the Pilot page shows the six handoff-quality measures; the Agents page lists the
  docs gaps (conversations handed off as `not_in_docs`).
- `integrations/crm_sync.py::connect` signs in with a consumer key
  (`SALESFORCE_CONSUMER_KEY`, `_SECRET`, `_DOMAIN`) or with a username, password and
  security token; new orgs need "Enable SOAP API login()" for the second. A third way
  needs no secret in the project: `SALESFORCE_CLI_ORG` names an org signed in to through
  the browser with the vendor's command-line tool (`sf org login web`). Steps in
  ADR 0019. A Sales task carries the account-owner brief.
- `experiments/analyze.py` also writes `gold.experiment_cohorts` (results by entry week)
  and revenue columns on `gold.experiment_results`.
- `agents/review.py`: thumbs up or down on a stored conversation; a thumbs down goes to
  `eval_candidates` (whose `cta_id` column then holds the conversation id).
- `api/exports.py`: the CS-platform export has `people` as well as companies and tasks.
  The field mapping is in the README.
- `app/diagrams.py`: draws the Mermaid diagrams of the docs with Graphviz, offline. It
  understands only what the docs use; anything else is shown as text. ADR 0022.
- `analytics/dictionary.py` and `dbt/column_glossary.yml`: `run.py docs` writes
  `docs/data-dictionary.md`. A test fails when a column has no definition. ADR 0021.
- `analytics/01_eda.ipynb`: the exploratory analysis with charts. Its libraries are the
  dependency group `notebook` (`uv run --group notebook ...`), not installed by default.
- `tests/test_app.py`: runs every page of the app on the small world, also with the
  network blocked, and plays the Live demo's scripted story.
- Live demo page (`app/views/demo.py`): accounts whose `activation_stalled` signal is
  firing come first. In replay mode the scripted story (`STORY`) has stored answers
  for the first five accounts in that list, and the other suggested questions for the
  first one. Stored answers match one exact conversation on one account as it is
  today: regenerating the data or advancing a day breaks the match (the agent then
  hands off as `agent_unavailable`). Store them again with one `--live` run of the
  same conversations (about 3 cents each).
- `config/job.yaml`: the ten lines of the role, in plain words, and the page that shows
  each. One source for the opening of every page (`app/ui.py::job_intro`), for the top of
  the Overview (`ui.what_this_is`: what this is, the workflow as cards, the role line by
  line) and for the menu's order (`app/main.py`). Page names are `ui.PAGE_NAMES`.
- `app/tour.py` and `config/tour.yaml`: the guided tour, a slim strip at the top of the
  page with Back, Next and End, one stop per page. It never covers the page. It names
  the platform and the team at a real company; the page's own opening says the rest. It
  starts by itself only on the hosted demo (`DSO_HOSTED`).
- How visitor-facing text is written (the owner's rules of 12 and 13 November 2026):
  complete sentences, every term defined where it is used, each team named as a team,
  never the words "cheap" or "thing", no line about the author. The browser-voice
  "Read aloud" button was removed (ADR 0023): the owner wants a recorded voice instead,
  which is not built yet.
- The agent on the public demo (ADR 0024, the owner's decision of 12 November 2026,
  which changes the brief's rule that the hosted app never calls the API): the stand-in
  by default; with `ANTHROPIC_API_KEY` set by the owner in the host's dashboard,
  `scripts/start-app.sh` starts it live with a budget of 5 dollars in total. The total
  is kept in the operational store (`agents/ledger.py`, table `llm_spend`, which the
  admin reset does not touch), so a restart cannot reset it. At the limit, and whenever
  the model cannot answer, the stand-in replies (`DSO_STAND_IN_WHEN_UNAVAILABLE`) and
  the Live demo page says so. To allow more: raise `LLM_BUDGET_USD` in the dashboard.
- `docs/screenshots/`: one picture per page.
- `docs/reviewer-guide.md`: a five-minute hands-on path for someone given the hosted
  link (also an expander at the top of the Overview page). Every example in it was
  checked against the stand-in, which is what the hosted app runs without a key. The hosted console's
  role passwords and the API token are generated by the host (`render.yaml`); only the
  owner can read them, in the host's dashboard. An Admin can reset the hosted store
  from the console (`scripts/seed_store.py --reset`).

When a dbt model gains a column: add its meaning (the model's `.yml`, the contract, or
`dbt/column_glossary.yml`) and run `uv run python run.py docs`, or two tests fail.

Hosting: a Render blueprint from the public repository. Render redeploys both services
on every push to `main` (seen in its deploy list as "Auto-Deploy"); a change to
`render.yaml` itself needs "Manual sync" on the blueprint page and an approval there.

Databricks: the prod pipeline has run on a Free Edition workspace (`DSO_ENV=prod uv run
python run.py pipeline`): 100 of 100 tests, contract 14 of 14, numbers match DuckDB.
Local sign-in is OAuth through the browser (`common/warehouse.py::databricks_token`);
`DATABRICKS_TOKEN` is only for CI. For that run `DATABASE_URL` pointed at the local
SQLite file.

Postgres: the operational store is tested on a real Postgres in CI (job
`store-on-postgres`: `tests/test_store.py` on both databases, two simulated days on the
local store, the seeding script run twice, then one more day with
`DSO_OPERATIONAL_STORE=env:DATABASE_URL`). `scripts/check_store.py` prints what a
run left in the store. The hosted app and API share a hosted Postgres created by
`render.yaml`; `scripts/seed_store.py` fills it once at start-up (`scripts/start-app.sh`,
`scripts/start-api.sh`), with a fallback to the local file. Trace export is tested
with a stand-in client (masking, and a failing service cannot break a run).

README pictures are in `docs/screenshots/` (three pages and `demo.gif`). Taking them has
two traps. The Live demo page writes real rows: each handoff adds a conversation
(`scenario = 'live_demo'`) and a task to the local store, so remove those rows afterwards
or the Overview counts stop matching the README. And a browser extension can draw its
icon (a real product's logo) in a corner of the page: check every picture and paint it
over before committing.

Ignore rules: anchor file names to the top folder (`/BRIEF.md`). Git on Windows matches
without regard to case, and an unanchored `BRIEF.md` once hid `prompts/brief.md`.
