<!-- Synthetic data, fictional company. See docs/change-control.md. -->

## What changes

<!-- One or two sentences. -->

## Why

<!-- The problem, and the evidence: experiment report, eval report, data-quality finding, complaint. -->

## What it affects

- [ ] Who is contacted (audience, exclusions, consent, frequency)
- [ ] What an agent may do (tools, escalation rules, prompts)
- [ ] How success is measured (metric, holdout, window)
- [ ] A production table or its contract
- [ ] A queue's volume or SLA
- [ ] None of the above (copy, docs, tests)

Plays, tables, queues and teams affected:

## Track

- [ ] Fast track (copy edit, threshold inside its agreed range, help article, eval case, capacity number)
- [ ] Full review (anything ticked in the first five boxes above)

## Checks

- [ ] `uv run python run.py test` passes
- [ ] `uv run python run.py pipeline` passes (data tests and contract)
- [ ] For agent changes: `uv run python run.py evals`, no loss in the hard-rule categories
- [ ] For play changes: `uv run python run.py specs` re-run; play `version` bumped if behaviour changes
- [ ] ADR added or updated for a decision

## Rollout and rollback

<!-- Slice first? Who was told? How is it undone? -->