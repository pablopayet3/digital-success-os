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

## Phase 3b: environments, secrets, CI, Databricks target (brief update v1.2, items 8, 10, 11)

### What works

- **Two environments, one codebase.** `DSO_ENV=dev` (default): DuckDB, SQLite, offline.
  `DSO_ENV=prod`: Databricks, Postgres. Described in `config/environments.yaml`, read by
  `common/settings.py`.
- **Secrets only from the environment.** `.env` locally (git-ignored), GitHub Secrets in
  CI. `.env.example` lists every variable with no values. A missing secret fails with a
  message naming the variable.
- **gitleaks** configured as a pre-commit hook and as a CI job over the full history.
- **CI workflow** (`.github/workflows/ci.yml`): on every pull request and push to main,
  secret scan, ruff, pytest, and `dbt build` against DuckDB. Runs offline, needs no secrets.
- **Portable SQL.** No DuckDB-only functions in any model. Differences are in
  `dbt/macros/portable.sql`. All 98 dbt nodes still pass on DuckDB, and a test scans the
  models for DuckDB-only syntax.
- **dbt `prod` target** for Databricks (`relay.bronze / silver / gold`), a loader that
  uploads landing files to a Unity Catalog volume, and a warehouse layer
  (`common/warehouse.py`) so scoring and the contract check run against either warehouse.
- 45 pytest tests pass.

### Not yet verified

- **Nothing has run against Databricks.** The adapter refuses to load without
  credentials. Expect small fixes on the first real run.
- **The CI workflow has not run.** It runs when the repo is pushed to GitHub.
- gitleaks itself is not installed on this machine; the hook installs it on first use.

### How to run

```
uv run python run.py pipeline                      # dev (default)
DSO_ENV=prod uv run python run.py pipeline         # prod, once the Databricks values are in .env
```

### The three decisions to defend

1. *Two environments, selected by one variable.* The live demo cannot depend on a network
   or a credential, and the system must also run on real services. One switch, one file
   that says what each environment uses, no flags scattered through the code.
2. *One set of dbt models for both warehouses.* Differences between DuckDB and Databricks
   live in a handful of macros. A test fails if a model uses DuckDB-only SQL. The
   alternative, two sets of models, guarantees they drift apart.
3. *The warehouse does SQL; Python runs outside it.* Free Edition restricts outbound
   internet, so LLM calls cannot run inside Databricks. Scoring and agents run in the app
   or the CI runner and read and write warehouse tables. That is also how it would be
   deployed at scale: an agent service next to the lakehouse, not inside it.

### Decisions recorded

ADRs 0011 (environments and secrets), 0012 (Databricks Free Edition, portable SQL).

## Phase 4: rules engine, journeys, consent, holdouts, the daily loop

### What works

- `uv run python run.py run-day` simulates one day end to end; `run-days 30` simulates
  thirty (about 15 seconds a day, then a closing pipeline run with all tests).
- **Play catalog as config**: seven plays in `config/plays.yaml`, each with trigger,
  audience, exclusions, intervention ladder (digital, agentic, human, and the rule for
  moving up), holdout, rollout stage (slice or full), success metric, owner, version.
  Journeys in `config/journeys.yaml`. A broken configuration is refused at start-up.
- **Rules engine**: daily, by priority, with a plain-word reason for every decision in
  the audit log (entered, held out, or kept out and why).
- **Holdout and rollout by hash**: deterministic, cannot be nudged, reshuffled only by a
  version bump. Holdouts are logged as "would have entered" and receive nothing.
- **Consent and frequency caps enforced in the engine**: opted-in and valid address only,
  opt-outs learned by the system honoured at once, two touches per contact per seven
  days across all plays, emails paused for accounts with no reachable admin.
- **Journey runner**: email (rendered to `data/outbox/`), in-app, agent, wait, branch,
  CTA, exit; goals that end a journey early; highest ladder tier recorded per enrolment.
- **Handoffs**: a typed handoff packet on every CTA (who, why, what was tried, the
  customer's own words, account snapshot, recommended next step, brief for Sales),
  routed to a queue with an SLA; capacity alerts when a queue overflows.
- **Return signal**: resolving a CTA resumes, ends or hands over the journey. "The agent
  should have handled this" lands in an evaluation review queue.
- **Closed loop**: simulated customers react to yesterday's touches; opens of journey
  emails flow back through the pipeline. After 12 days, 34% of treated stalled accounts
  had completed setup against 0% of the holdout.
- **Operational store** on SQLAlchemy (SQLite now, Postgres by URL), copied into
  `bronze.ops_*` on every pipeline run.
- **Scale the pattern**: adding `pooled` to `config/rollout.yaml` runs the same plays on
  that segment (tested).
- 64 pytest tests pass.

### Not yet there

- The agent step has no agent behind it until Phase 5. Until then it takes the documented
  fallback: an agent that cannot run hands off to a human.
- Postgres has not been run against (needs a `DATABASE_URL`).

### How to run

```
uv run python run.py data && uv run python run.py pipeline && uv run python run.py train
uv run python run.py run-days 30
```

### The three decisions to defend

1. *Plays are config; guardrails are code.* A play owner changes a threshold, an audience
   or a holdout by editing a file. Consent, frequency caps and exclusivity are enforced by
   the engine for every play, so no journey can forget them.
2. *Holdout by hash, and a holdout is a real enrolment.* Deterministic assignment cannot be
   gamed and never reshuffles. Holdout accounts are reserved for the measurement window so
   another play cannot contaminate the comparison. 50% in the pilot, because a pilot exists
   to learn.
3. *Live state in an operational store, analysis in the warehouse.* Enrolments and CTAs
   change one row at a time and have several writers; that is not what a warehouse is for.
   The store is copied into bronze daily, so metrics are still computed in one place.

### More to be able to explain

- **Why every exclusion is logged.** "Why did this account not get the play?" is the
  question a CSM, a seller or a privacy officer will ask. The audit log answers it.
- **Why the frequency cap sits above plays.** Each play looks reasonable on its own; the
  customer experiences the sum.
- **What the return signal is.** The human's outcome and reason code decide what happens
  next (re-enter, exit, Sales owns it). Without it a handoff is a dead end and the system
  never learns which handoffs were unnecessary.
- **Why the simulated effect sizes are in a config file.** Any lift this demo shows comes
  from `config/sim_effects.yaml`. Saying so plainly is the difference between a demo of a
  measurement system and a fake result.
- **A bug the loop found.** The warehouse loader guessed the CSV format from the first
  rows. It failed on the first email subject containing a comma. The format is now stated
  explicitly.

### Decisions recorded

ADRs 0013 (operational store), 0014 (plays as config, deterministic holdouts, guardrails).

---

## Phase 5: agents and human fallback, with LLM cost controls

### What works

- **Onboarding agent** (`agents/onboarding.py`): a conversation with a customer admin. It
  has three read tools (setup status, account context, help-centre search) and two
  write tools (hand off, log outcome), all bound to the one account in the conversation.
- **Retrieval** (`agents/retrieval.py`): BM25 keyword search over 23 fictional help
  articles in `kb/`, with a rule that says whether any article covers the question.
- **Hard escalation rules in code** (`agents/escalation.py`): asks for a person,
  frustration, pricing (to Sales), contract or refund or legal, not in the docs, tool
  failure, repeated question, model unavailable. Pricing and "I want a person" never
  reach the agent model.
- **Mailbox triage agent** (`agents/mailbox.py`): a small model classifies every reply
  (eight intents, sentiment, confidence); rules in `config/routing.yaml` decide the action.
  An unsubscribe takes effect the same day; a complaint opens a high-priority task and
  pauses the account's emails; an unsure classification goes to a person.
- **Account briefs for Sales** (`agents/briefs.py`): written by the model from the
  account's facts; code rejects any brief containing a number that is not in the data
  and falls back to a template.
- **Feedback classification** (`agents/feedback.py`): sentiment and theme of recent NPS
  comments and high-priority tickets.
- **Cost controls** (`agents/llm.py`): every response cached; offline by default; a run
  stops at `MAX_LLM_CALLS_PER_RUN` or `LLM_BUDGET_USD` and prints the spend; at most 50
  agent conversations per run; models chosen in `config/llm.yaml`.
- **Traces** (`agents/tracing.py`): one JSON file per conversation in `data/traces/`
  (messages, tool calls, retrieved articles, decision, cost, latency) with names and
  email addresses masked.
- **Stand-in mode** (`agents/stand_in.py`): a rule-based stand-in plays the model so the
  whole flow runs with no key. It is labelled "stand-in" in every trace and on screen.
- **Docs**: `docs/human-fallback.md`, and one generated spec per play in
  `docs/play-specs/` (a test fails if a spec no longer matches the config).
- 115 pytest tests pass.

### Not yet there

- **No real model call has been made.** There is no API key on the build machine. The
  request shapes follow the API reference; the first live run may need small fixes.
  Until then the demo uses the stand-in, which shows the flow but says nothing about
  answer quality.
- LangSmith export is written but not run (needs a key). JSON traces work.

### How to run

```
uv run python run.py run-days 30     # agents and mailbox triage run inside each day
uv run python run.py specs           # rebuild docs/play-specs/
```

For a live run that fills the cache with real responses (about 1 to 3 dollars, stops
at 5): put `ANTHROPIC_API_KEY` in `.env`, set `DSO_OFFLINE_MODE=false` and
`DSO_LLM_STAND_IN=false`, run the simulation and the evals once, then set both back.
From then on offline mode replays the real responses for free.

### The three decisions to defend

1. *The rules that matter are code, not prompt.* A prompt asks; code guarantees. The
   agent cannot quote a price because a pricing message never reaches it. Each rule has a
   test that runs without a model. The cost is over-escalation, which is measured by the
   outcome "the agent should have handled this".
2. *The LLM proposes, rules decide.* In the mailbox the model only labels a reply. What
   happens to an "unsubscribe" or a complaint is the same every time and is written in a
   config file a non-engineer can read. Low confidence goes to a person.
3. *Cost is designed in, not monitored afterwards.* One module calls the API. It caches
   everything, refuses to call when offline, and stops at a budget. The demo, CI and the
   hosted app hold no key. Small model for labelling, stronger model only where a
   customer reads the output.

### More to be able to explain

- **Why BM25 and not embeddings.** 23 articles; free, offline, and you can read why a
  match happened. The important part is not the ranking but the "does anything cover
  this question" rule, because that is what triggers a handoff (ADR 0002).
- **Why `converse()` has no side effects.** The same function serves the journey runner,
  the mailbox, the evals and the live demo. Only the caller creates a task or writes to
  the database.
- **Why the brief is checked for numbers.** A model that invents "they will add 40
  seats" in a sales brief does real damage. Every number in a brief must be found in
  the account's data, or the template is used.
- **What the stand-in is and is not.** It is keyword rules in the model's seat so the
  flow can run. It proves the plumbing, the rules and the handoffs. It proves nothing
  about how well a real model answers, and every screen says which one produced the output.
- **Prompt versions.** `prompts/onboarding_agent/v1.md` and `v2.md` with a changelog;
  the version in use is config, and every conversation records it. Phase 6 compares them.

### Decisions recorded

ADRs 0002 (BM25 retrieval), 0003 (escalation rules in code), 0015 (LLM cost controls,
model choice and the stand-in).

---

## Phase 6: evals and experiments

### What works

- **Outcome tables in the warehouse**: `gold.metrics_play_outcomes` (one row per
  enrolment, treatment and holdout, six yes/no outcomes over the 30-day window),
  `metrics_play_summary`, `metrics_play_ladder` (per rung: digital, agentic, human),
  `metrics_handoffs` (pickup time, SLA breaches, outcomes), `metrics_agent`.
- **Experiment analysis** (`experiments/analyze.py`): per play, treatment against
  holdout on the metric declared in the play config; lift with a 95% interval, a
  two-proportion z-test, a sample-ratio check, the smallest detectable lift, weekly
  cohorts, results per ladder rung, revenue retained and expansion won per group, and a
  written recommendation. Results also land in `gold.experiment_results` for the app.
- **Evaluation suite** (`evals/`): 44 cases (30 agent conversations, 10 mailbox replies,
  4 briefs). Code checks first, LLM judge second. Each agent case runs with both prompt
  versions. The mailbox classifier is scored against the simulator's labels with a
  confusion matrix.
- **Play specs now list their own eval cases**, read from the case files.
- Reports: `experiments/reports/experiment-report.md`, `evals/reports/eval-report.md`.

### Not yet there

- The eval report was produced with the stand-in model. It proves the harness and the
  rules. The prompt comparison and the judge need one live run with an API key.

### How to run

```
uv run python run.py experiments
uv run python run.py evals
```

### The three decisions to defend

1. *A 50% holdout and leading indicators for the pilot.* With a few dozen accounts and
   30 days, a 10% holdout and a churn metric would show nothing. A pilot exists to learn,
   so half are held back and each play is judged on something that can move in 30 days.
   Retention is a guardrail. After the pilot the holdout drops to 10% and stays.
2. *Three protections against fooling ourselves.* A check that the split is the one
   designed; a minimum sample before any verdict; and the smallest lift the sample could
   have detected, printed next to every "no effect".
3. *Code checks first, judge second.* Anything that must always happen is checked by
   code, for free, the same way every time. The judge only scores the wording of answers
   that already passed. A safety behaviour never depends on a model's opinion.

### More to be able to explain

- **The z-test in one sentence.** If the play did nothing, how often would two groups of
  this size differ by this much? If the answer is under 5%, we call it working.
- **Sample ratio mismatch.** Assignment is by hash, so a 50% design should give about
  50%. If it gives 60/40 on a thousand accounts, something is filtering one group (for
  example an exclusion applied after assignment) and the comparison is void.
- **Why outcomes are computed for both groups in dbt.** Same definition, same data, same
  code path. The only difference between the groups is the play.
- **Reading the ladder table.** Accounts that reached the human rung are the hard cases.
  A lower rate there is selection, not a verdict on people.
- **What the stand-in eval does and does not show.** It shows every hard rule fires and
  routes correctly. It cannot show answer quality.

### Decisions recorded

ADRs 0016 (experiment design for the pilot), 0017 (evals: code checks first, judge second).
