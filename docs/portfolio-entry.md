# Portfolio entry

Synthetic data, fictional company. Copy for the portfolio site. Stat badges are from the
clean run of `uv run python run.py demo`; replace them if the run is repeated.

**Title:** Digital Success OS (mini)

**Tagline:** Customer signals → plays → AI agents → human fallback → measured against a holdout.

**Metadata:** Type: end-to-end system · Code level: full code · Model: Claude (Anthropic API)

**Stat badges**

| Badge | Value |
|---|---|
| Accounts simulated | 1,200 |
| Events processed | 617,001 kept, 8,388 rejected with a reason |
| Data tests passing | 100 of 100, plus a 14-check data contract |
| Plays | 7, each with an owner, a success metric and a holdout |
| Agent evaluation cases | 44 |
| Agent handoff rate | 38% (20 of 52 conversations) |
| Lift against holdout | +35 points on setup completion (onboarding rescue), 95% interval +21 to +48 |
| Automated tests | 138 |

Until one run with an API key, add this line under the badges: "Agent answers in this run
come from a labelled rule-based stand-in; the lift is a simulation assumption coming back
out through a real measurement pipeline."

## Problem

A software company has more customers than success managers. For the uncovered accounts,
the signals that someone is stuck, unhappy or ready to grow sit in separate systems, and
when automation does reach a customer nobody can say whether it helped. This project is a
working answer on fictional data: one pipeline from raw signal to measured outcome, with
a person in the loop wherever one changes the result.

## Architecture

Telemetry and CRM files land in a validated ingest with a dead-letter queue. dbt builds
bronze, silver and gold tables with 100 tests and a data contract on the production
table. Signals, an explainable health score and two models flag accounts by the team's
capacity. A rules engine assigns accounts to plays with consent, a frequency cap and a
holdout by hash. Journeys step through digital, agentic and human rungs. An onboarding
agent answers from a help centre and hands off under rules written in code. Every handoff
carries a typed packet, and the person's outcome returns to the journey. Outcomes are
computed in the warehouse and each play is compared with its holdout.

## Under the hood

1. **Ingestion and dead letter** (`ingest/schemas.py`, `ingest/load.py`): every event is validated; rejects are kept with a reason code.
2. **The gold table and its contract** (`dbt/models/marts/account_daily.sql`, `contracts/`): one row per account per day; a check fails the run on a missing or undocumented column.
3. **Signals and health** (`dbt/models/marts/signals.sql`, `config/health.yaml`): plain rules with evidence in words.
4. **Rules engine and holdout** (`engine/rules.py`, `engine/assignment.py`): plays as configuration, assignment by hash, every decision logged.
5. **Agent tools and escalation rules** (`agents/tools.py`, `agents/escalation.py`): tools bound to one account; pricing never reaches the model.
6. **Handoff packet and return signal** (`engine/handoff.py`): what travels to the person, and what comes back.
7. **Evals** (`evals/run.py`): code checks first, an LLM judge second, prompt versions on the same cases.
8. **Experiment statistics** (`experiments/analyze.py`): lift with an interval, a split check, the smallest detectable lift, a written decision rule.

## How I built it

- Escalation rules are code, not prompt: a prompt asks, code guarantees (ADR 0003).
- Accounts are flagged by what the team can work, not by a fixed score (ADR 0004).
- The simulated world reacts to touches, so lift is measured from telemetry, and the report says plainly that the effect sizes are assumptions (ADR 0005, 0016).
- The data contract is checked in both directions (ADR 0010).
- Plays are configuration; guardrails are engine code that no play can skip (ADR 0014).
- LLM cost is designed in: cache, offline by default, a budget that stops the run (ADR 0015).
- When the split check fired on my own data, I investigated before reading the result (ADR 0016).

## Tools

Python, DuckDB, dbt, scikit-learn, pydantic, SQLAlchemy, FastAPI, Streamlit, the Claude
API, pytest, ruff, GitHub Actions, Docker.

## Output

Screenshots to take from the app: Overview, an account page, Plays and experiments (the
interval chart), a conversation with its handoff, a handoff packet in the Human console,
Data quality, Pilot. Plus `evals/reports/eval-report.md` and
`experiments/reports/experiment-report.md`.