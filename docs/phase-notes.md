# Phase notes

Synthetic data, fictional company. One section per phase: what works, how to run it, the
three design decisions to defend in the interview, and more detail to be able to explain.

## The three decisions to defend, per phase

**Phase 1: synthetic data**
1. *Hidden ground truth.* Accounts have hidden traits that really drive usage, expansion
   and churn. So a model that finds patterns is finding real ones, and I can check it
   against the truth. The traits never reach the pipeline.
2. *180 days, labels from the CRM.* A 90-day outcome needs 90 observed days. I lengthened
   history so models train on outcomes the CRM recorded, with a real time-based split,
   instead of on the simulator's answer key.
3. *A world that moves one day at a time.* Customers can react to plays, so lift is
   measured from pipeline output rather than added to a spreadsheet afterwards.

**Phase 2: pipeline and data quality**
1. *Two kinds of bad data, two treatments.* Unusable rows are stopped at ingest and kept in
   a dead-letter queue with a reason. Usable-but-messy rows are repaired in silver, where
   the repair is visible and tested.
2. *One production table per grain, with a contract checked by code.* `account_daily` is
   the only place consumers read accounts from. Missing and undocumented columns both fail.
3. *Prove that data quality works.* The generator logs what it breaks; tests show the
   pipeline caught exactly that. Passing tests on clean data proves nothing.

**Phase 3: signals, health, models**
1. *Flag as many accounts as people can act on.* The cut-off is redrawn every day at the
   team's capacity (40 churn conversations, 60 expansion briefs), not at an accuracy
   optimum. Precision at that cut-off is what the team will actually experience.
2. *An explainable model in production, a stronger one as a benchmark.* Logistic
   regression gives every flag a reason a CSM can read. Gradient boosting ranks better on
   churn (AUC 0.79 against 0.72). I state the price and when I would switch.
3. *Health score and churn model are different things, kept separate.* The health score
   is a description with weights the business chose and five visible components. The model
   learns its own weights from outcomes. Lifecycle stage has one value per account, by
   documented precedence.

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

## Phase 3: signals, health, segmentation and models

### What works

- `uv run python run.py train` trains both models, writes their model cards, then
  refreshes scores, lifecycle stages and signals.
- **Health score** (0 to 100) with five stored components and a band. Today: 400 green,
  512 yellow, 46 red. Weights and bands are in `config/health.yaml`.
- **Lifecycle stage** per account per day, six stages, first matching rule wins
  (`docs/metrics.md`).
- **Signals**: ten rules in SQL, 89,458 rows (one per account, day and signal), each with
  the number that fired it and the evidence in words.
- **Churn model**: AUC 0.715 on a later-in-time test snapshot; 30% precision in the top
  10% against a 10% base rate. At the capacity cut-off (40 accounts): 27.5% precision
  against a 9.3% base rate. Gradient boosting benchmark: AUC 0.788.
- **Expansion model**: AUC 0.861; 48% precision in the top 10% against 12%. At the
  capacity cut-off (60 accounts): 48% precision against 13%.
- Every score has **plain-word reasons** ("few seats active, admin rarely logs in, low
  NPS"). Model cards are generated from the training run (`docs/model-cards/`).
- **Segmentation**: value tier (rule on ARR) x lifecycle stage x behaviour cluster
  (k-means, four named clusters) in `gold.account_current`.
- **Exploratory analysis** (`docs/eda-report.md`): seat pressure lifts expansion 5.2
  times, the churn flag lifts churn 2.9 times, stalled onboarding 1.8 times. Red-health
  accounts churn at 23% against 5% for green.
- The pipeline runs in two dbt stages with scoring in between, and still works when no
  model has been trained. 36 pytest tests, 77 dbt tests, contract 14 of 14.

### How to run

```
uv run python run.py data
uv run python run.py pipeline
uv run python run.py train
uv run python -m analytics.eda
```

### More to be able to explain

1. **Why precision in the top 10%, not accuracy.** 90% of accounts do not churn, so a
   model that says "nobody churns" is 90% accurate and useless. What matters is how many
   of the accounts the team is sent really are at risk.
2. **Why the cut-off moves.** With a fixed score, 40 accounts were flagged on the test day
   and 74 three months later, because the customer base grew. Capacity is a queue size,
   so the cut-off is the score of the 40th account each day.
3. **Calibration.** The model card splits accounts into five groups by score and compares
   predicted with observed rates. A score of 30% should mean about 30% churn.
4. **Leakage guards.** Features come only from the gold table as it stood on the snapshot
   day. Labels come from the CRM. The test snapshot is later than every training row. A
   test asserts that no feature is a hidden trait.
5. **Honest limits.** Same accounts in train and test on different days; a few hundred
   positives; in-sample scores inside the training window. All in the model cards.
6. **Validation against hidden truth.** Only possible in a simulation: the churn score
   correlates -0.62 with the hidden momentum that actually drives churn.
7. **Signals are rules, on purpose.** A rule can be read, argued with and changed by the
   business. The two model signals sit next to eight plain rules in the same table.

### Decisions recorded

ADR 0004 (cut-off by capacity, explainable model in production). Definitions in
`docs/metrics.md`. Model cards in `docs/model-cards/`.
