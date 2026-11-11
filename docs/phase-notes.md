# Phase notes

Synthetic data, fictional company. One section per phase: what works, how to run it, and
what to be able to explain in the interview.

## Phase 1: skeleton and synthetic data

### What works

- `uv run python run.py data` builds a fictional customer base in about 25 seconds:
  1,200 accounts (1,092 signed up by the end of history), 5,583 contacts, 180 days of
  product telemetry (626,796 events), 3,376 tickets, 1,669 NPS responses, 32,094 emails
  and 460 mailbox replies.
- The same seed always gives byte-identical files.
- 11 tests pass (`uv run python run.py test`), and the linter is clean.
- A generation report (`data/ground_truth/generation_report.md`) shows row counts, the
  injected data problems, and how many accounts would qualify for each signal.

### How to run

```
uv sync
uv run python run.py data
uv run python run.py test
```

### What to be able to explain

1. **Why synthetic data has hidden ground truth.** Each account has three hidden traits
   (engagement, fit, growth). They drive usage, sentiment, expansion and churn. Because
   the patterns are really there, a model that finds them is doing real work, and I can
   check its scores against the truth. The traits are never exported to the pipeline.
2. **Usage drops before churn, on purpose.** A hidden "momentum" follows product fit and
   takes hits from shocks and support problems. Usage follows momentum; churn risk rises
   as it falls. That is the causal story a churn model and a usage-drop signal rely on.
3. **Why 180 days and not 120.** Churn "within 90 days" needs 90 observed days after the
   snapshot. With 180 days, labels come from the CRM (status, churn date, closed-won
   expansion opportunities), as in real life, and the train/test split is by time.
4. **Why 1,200 accounts.** Seven plays, one segment, each with a holdout. I sized the
   world so every play has enough accounts for a test, and the report proves it before
   any pipeline exists (77 stalled onboardings, 57 usage drops, 75 under seat pressure
   on the last day alone).
5. **Messy data is injected deliberately and logged.** About 1% of events lack an account
   id, some are duplicated, some have future timestamps or unknown names, a few lines are
   broken JSON, one day arrives three days late, and the CRM has duplicate contacts and
   inconsistent persona spellings. The log of what was injected lets Phase 2 prove the
   pipeline caught exactly those rows.
6. **A real governance gap is built in.** Replies to lifecycle emails land in a shared
   mailbox that nobody read before the pilot. So some contacts who replied "unsubscribe"
   are still opted in, and some who left the company are still listed as valid admins.
   The mailbox triage agent in Phase 5 fixes this.
7. **The world moves one day at a time.** `World.step()` simulates a day. From Phase 4 the
   engine passes in the touches it delivered, so customers can react, and lift is measured
   from pipeline output rather than added to a spreadsheet afterwards.
8. **Why a Python task runner.** There is no `make` on Windows. `run.py` works anywhere;
   the Makefile forwards to it.

### Decisions recorded

ADRs 0001 (DuckDB, dbt, uv), 0005 (simulated world and treatment effects), 0006 (task
runner), 0007 (history length, volumes, labels), 0008 (template text).
