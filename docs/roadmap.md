# Roadmap

Synthetic data, fictional company. Now, next, later. An item moves left only with
evidence from the experiment report.

## Now: the pilot on uncovered accounts

- Seven plays live on the uncovered segment; five on a full test, two on a 10% slice.
- Onboarding agent and mailbox triage agent, with hard escalation rules and a human console.
- Daily pipeline with data tests, a contract on the production table, and freshness checks.
- Experiment report per play; evaluation report per prompt version.
- One live run with a real model, cached and replayed offline. (Done: the reports and
  every stored conversation come from it.)
- The production profile, run for real: the same models on a lakehouse warehouse, the
  operational store on Postgres, a scheduled daily run, a hosted app and API.

## Next: prove, then widen

- Scale the plays that worked to the pooled segment (a configuration change), with a 10% holdout.
- Move edition upgrade and cross-product from slice to full test.
- Work the review queue every week: turn each unnecessary handoff and each thumbs-down
  conversation into an evaluation case with an expected behaviour.
- Write the help articles the docs-gap list asks for most.
- Load the CS-platform export into a tenant. (The CRM push has run for real against a
  developer org; next there is custom fields instead of a text description.)

## Later: what scale would need

- Streaming ingestion for signals that should not wait a day (a complaint, a failed payment).
- A feature store, so the models and the plays read the same definitions.
- Embedding retrieval with re-ranking once the help centre outgrows keyword search.
- A proper experimentation platform: sequential tests, variance reduction, a 90-day revenue window.
- Agents for renewal preparation and for drafting replies that a person approves.
- Per-region consent rules and data residency.

## Not planned

- Agents that quote prices or change subscriptions.
- Fully automated outreach to accounts with a named success manager.
