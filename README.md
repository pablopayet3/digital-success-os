# Digital Success OS (mini)

> **Synthetic data, fictional company.** "Lumen Labs" and its product "Relay" do not exist.
> Every account, contact, event and message in this repo is generated.

Customer signals → plays → AI agents → human fallback → measured against a holdout.

A small, working version of a digital customer-success operating system: raw product
telemetry and CRM data land in a pipeline, get cleaned into production tables with
data-quality tests, become signals and model scores, and trigger plays (a journey, an AI
agent, or a task for a human). When the agent cannot help, it hands off with full context,
and the human's outcome comes back into the system. Every play has a holdout, so the
system can show what it actually moved.

## Status

Built in phases. This README is a stub until Phase 8.

| Phase | What | Status |
|---|---|---|
| 1 | Skeleton and synthetic data | done |
| 2 | Pipeline and data quality | done |
| 3 | Signals, health, models | done |
| 4 | Rules engine, journeys, consent | next |
| 5 | Agents and human fallback | |
| 6 | Evals and experiments | |
| 7 | App and API | |
| 8 | Docs, demo, portfolio | |

## How to run

Needs [uv](https://docs.astral.sh/uv/) and Python 3.12.

```
uv sync
uv run python run.py data      # generate the synthetic world (about 25 seconds)
uv run python run.py pipeline  # ingest, build silver and gold, run the data tests
uv run python run.py train     # train the churn and expansion models, refresh signals
uv run python run.py test      # run the tests
```

Definitions of every metric, the health score and the lifecycle stages are in
[docs/metrics.md](docs/metrics.md). Model cards are in [docs/model-cards](docs/model-cards/).
What the data shows is in [docs/eda-report.md](docs/eda-report.md).

`uv run python run.py data --profile small` builds a smaller world in about 5 seconds.

On Windows, keep the project in a short folder path (for example
`C:\Users\you\Projects\digital-success-os`). Deeply nested folders can push dbt's file
names past the 260-character limit.

## The pipeline (Phase 2)

```
data/landing/  ──ingest──►  bronze  ──dbt──►  silver  ──dbt──►  gold
                  │                    (clean, typed,        (dim_account, dim_contact,
                  ▼                     de-duplicated)        fct_usage_daily, fct_prerequisites,
        data/dead_letter/                                     account_daily, dq_summary)
        (rejected rows + reason)
```

- Events are validated on the way in. Unusable rows go to a dead-letter queue with a
  reason. Loads are idempotent.
- dbt cleans (silver) and shapes (gold), with 63 data tests and a freshness check.
- `gold.account_daily` is the production table: one row per account per day, with a
  [data contract](contracts/account_daily.yaml) checked by code on every run.

## What Phase 1 produces

`data/landing/` is what the company's systems would export; the pipeline reads only this.

| File | What it is |
|---|---|
| `events/YYYY-MM-DD.jsonl` | Product telemetry, one file per day (about 500,000 events over 180 days) |
| `crm_accounts.csv`, `crm_contacts.csv`, `crm_opportunities.csv` | CRM export |
| `licenses.csv` | Seats licensed and assigned, per account per day |
| `tickets.csv` | Support tickets with free text |
| `nps.csv` | NPS scores and comments |
| `email_engagement.csv` | Lifecycle emails sent, opened, clicked, bounced |
| `mailbox/*.json` | Replies to those emails, landing in a shared mailbox |

`data/ground_truth/` is the answer key: hidden traits, classifier labels, the list of data
problems injected on purpose, and `generation_report.md`. Nothing downstream may read it
except validation and evaluation code.

## Layout

```
config/      world.yaml (generator), rollout.yaml (pilot segments, offline mode)
common/      paths and config loading
synth/       the world simulator                                   Phase 1
ingest/      validation, dead letter, bronze loads, dbt runner     Phase 2
dbt/         silver and gold models, tests, sources                Phase 2
contracts/   data contract for account_daily and its checker       Phase 2
analytics/                                                         Phase 3
engine/ agents/ prompts/ kb/                                       Phases 4 and 5
evals/ experiments/ api/ app/                                      Phases 5 to 7
docs/        decisions (ADRs), phase notes, and later the operating documents
tests/
```

Design decisions are recorded in [docs/decisions](docs/decisions/). What each phase
delivered is in [docs/phase-notes.md](docs/phase-notes.md).
