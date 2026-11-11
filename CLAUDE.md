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
uv run python run.py test
uv run python run.py lint
```

`run.py` is the entry point (there is no `make` on the Windows machine this was built on).
The `Makefile` only forwards to it.

## Decisions that differ from the brief

| Brief | What we do | ADR |
|---|---|---|
| Makefile entry point | `run.py`, with the Makefile as a thin wrapper | 0006 |
| Generate 120 days up front, add treatment effects to outcomes afterwards | A day-by-day world (`World.step`) that reacts to touches from Phase 4 | 0005 |
| 120 days, labels from hidden ground truth | 180 days; labels from churn and expansion recorded in the CRM files | 0007 |
| About 600 accounts | 1,200 (1,092 signed up by the end of history) | 0007 |
| Seven sources | Plus `crm_opportunities.csv`, `email_engagement.csv`, and `product_user_id` on contacts | 0007 |
| (not stated) | No LLM in the generator: templates plus noise | 0008 |

Flagged for later phases: operational state in SQLite rather than the DuckDB file
(Phase 4), JSON traces only (Phase 5), 50% holdout and leading-indicator metrics for the
pilot (Phase 6).

## Phases

1. Skeleton and synthetic data: **done**
2. Pipeline and data quality (ingest, dbt bronze/silver/gold, tests, contract)
3. Signals, health score, segmentation, churn and expansion models
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
- `tests/test_synth.py`: Phase 1 tests.
