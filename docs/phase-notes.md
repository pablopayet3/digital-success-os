# Phase notes

Synthetic data, fictional company. One section per phase: what works, how to run it, and
what to be able to explain in the interview.

## Phase 1: skeleton and synthetic data

### What works

- `uv run python run.py data` builds a fictional customer base in about 25 seconds:
  1,200 accounts (1,091 signed up by the end of history), 5,534 contacts, 180 days of
  product telemetry (496,405 events), 3,373 tickets, 1,602 NPS responses, 31,652 emails
  and 482 mailbox replies.
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
   any pipeline exists (76 stalled onboardings, 55 usage drops, 61 under seat pressure
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

## Phase 2: pipeline and data quality

### What works

- `uv run python run.py pipeline` takes the landing files to tested gold tables in about
  45 seconds the first time (about 20 seconds once the events are loaded).
- **Ingest**: 498,812 event lines read; 492,197 loaded to bronze; 6,615 rejected to the
  dead-letter queue with a reason (4,852 missing account id, 1,531 unknown event name,
  232 broken JSON). Running it again loads nothing.
- **Silver** (dbt): 2,407 duplicate events removed, 967 future-dated events removed, 615
  late-arriving events kept under their true date, 55 duplicate contacts removed, 429
  persona tags normalised.
- **Gold** (dbt): `dim_account`, `dim_contact`, `fct_usage_daily`, `fct_prerequisites`,
  `account_daily` (the production table, 125,348 rows, 50 columns) and `dq_summary`.
- **63 dbt tests pass** (unique, not null, relationships, accepted values, three custom
  tests), source freshness passes, and the **data contract** check passes 12 of 12.
- 24 pytest tests pass. The key ones prove that the dead-letter counts, the duplicates
  removed and the contacts cleaned equal the generator's issue log exactly.

### How to run

```
uv run python run.py data
uv run python run.py pipeline
uv run python run.py test
```

To look inside the warehouse: `uv run python -c "import duckdb; print(duckdb.connect('data/warehouse.duckdb').sql('select * from gold.dq_summary'))"`

### What to be able to explain

1. **Medallion layers.** Bronze is raw and append-only (what arrived). Silver is clean,
   typed and de-duplicated (what is true). Gold is shaped for use (what people query).
   Same pattern as a cloud lakehouse; here it is DuckDB and dbt.
2. **Two kinds of bad data, two treatments.** Unusable rows (no account id, unknown event,
   broken JSON) are stopped at ingest and kept in a dead-letter queue with a reason, so
   they can be fixed and replayed. Usable-but-messy rows (duplicates, wrong clocks, late
   arrivals, messy CRM entries) are loaded and repaired in silver, where the repair is
   visible and tested.
3. **Idempotent loading.** A load log remembers which files are in. Re-running is safe.
4. **I can prove data quality works.** The generator logs what it injects; the tests check
   the pipeline caught exactly that. Most demos only show that tests pass on clean data.
5. **One production table per grain, with a contract.** `account_daily` is one row per
   account per day. The contract names the owner, the grain, every column and its
   definition, quality rules, freshness, consumers and the change policy. Code checks the
   live table against it on every run, in both directions (missing and undocumented
   columns both fail).
6. **Why "five users" comes from the licence snapshot.** Events can be lost (about 1.3%
   were rejected). A setup step read from events can look undone when it is done. Seats
   come from the system of record, so I read the step from there. In gold, seats match
   the simulator exactly; setup steps read from events match for over 95% of accounts.
   That gap is the cost of lost events, and it is the argument for replaying dead letters.
7. **"Today" is data, not the clock.** The warehouse treats the latest licence snapshot as
   today, because the data runs on a simulated calendar. Freshness is measured on real
   load time, which is what a missed pipeline run would show up in.
8. **The pipeline measures the truth.** Signal counts computed from gold match the
   simulator's own counts (76 stalled onboardings in both).

### Decisions recorded

ADRs 0009 (validation, dead letter, where cleaning happens), 0010 (production table and
contract).
