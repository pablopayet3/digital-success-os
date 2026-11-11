# 0009: Validate events at the door, clean everything else in dbt

Status: accepted (Phase 2). Synthetic data, fictional company.

## Context

Raw data arrives in two shapes. Product events are a stream: one file per day, append-only,
high volume, produced by code we do not control. CRM, licence, support, NPS, email and
mailbox files are snapshots: the full current state, replaced each day.

Some of it is wrong. In this demo about 1.3% of event lines are unusable (no account id,
an unknown event name, or broken JSON), some events are delivered twice, some carry a date
two years in the future, one day arrives three days late, and the CRM has duplicate
contacts and inconsistent persona spellings.

## Options

1. Load everything as it is and clean it all in SQL. Simple, but unusable rows sit in the
   warehouse and every query has to remember to exclude them.
2. Reject anything imperfect at ingest. Clean tables, but good data gets thrown away for
   problems that are easy to repair (a duplicate, a late arrival).
3. **Split by kind of problem.** Rows that cannot be used at all are stopped at the door.
   Rows that are usable but messy are loaded and repaired in dbt, where the repair is
   visible and tested.

## Decision

Option 3.

- **At ingest** (`ingest/schemas.py`, a pydantic model): an event must have an id, a
  timestamp, a valid account id and a known event name. Anything else goes to the
  dead-letter queue: a table (`bronze.dead_letter`) and a file per day
  (`data/dead_letter/events/`), each row with a short reason code and the raw line, so it
  can be fixed and replayed. Nothing is dropped silently.
- **Idempotent loads**: `bronze._load_log` records each event file once it is loaded.
  Running the loader again loads nothing.
- **Snapshots are loaded as-is**, all columns as text, replaced on every run.
- **In silver (dbt)**: duplicates removed by event id, future-dated events filtered,
  late events kept under their true date, emails lowercased, personas normalised,
  duplicate contacts collapsed.
- **In gold**: `dq_summary` counts everything caught at each stage. The app shows it.
- The same validation function will serve the webhook endpoint in Phase 7.

## Consequences

- The tests can prove the pipeline caught exactly what the generator injected: the
  dead-letter counts equal the generator's issue log, row for row.
- A rejected event can hide a real fact. If a "SSO configured" event is dead-lettered, the
  account looks one setup step behind. So the five-users step is read from the licence
  snapshot (the system of record) rather than by counting invite events, and the
  data-requirements document asks for entitlement snapshots wherever they exist.
- "Today" in the warehouse is the latest licence snapshot date, never the real clock,
  because the data runs on a simulated calendar.

## Revisit if

Dead-letter volume grows beyond a few percent (then the fix belongs with the team that
emits the events), or events need to arrive in real time rather than as daily files.
