# 0020: The pilot readiness checklist is answered from data, not ticked by hand

Status: accepted. Synthetic data, fictional company.

## Context

`docs/pilot-plan.md` has a readiness checklist: what must be true before a play moves
from a 10% slice to a full test. A checklist in a document is ticked once and then
believed. Three weeks later a test is failing or a queue is under water, and the ticks
still say "ready".

## Options

1. Keep the checklist as a document that play owners tick.
2. **Answer each line from the live data every time the Pilot page is opened.**
3. A scheduled job that writes a readiness table to the warehouse.

## Decision

Option 2, in `engine/pilot.py`. One small function per line, each returning whether the
line holds and the evidence in words:

| Line | Where the answer comes from |
|---|---|
| Data tests pass and the data is fresh | `gold.dq_test_results`, `gold.dq_contract_checks`, `gold.dq_freshness` |
| Consent and the frequency cap are enforced | What was actually sent: the most touches any contact received in seven days, and emails dated after an opt-out |
| The agent passes its evaluation | `evals/reports/eval-results.json`, for the prompt in use |
| The human queues can take the work | Open tasks per queue against that queue's daily capacity |
| Handoffs come back with a return signal | Every closed task carries an outcome and the journey's next step |
| The results tables are built and current | The tables the dashboards read exist, have rows and are as of today |

Two lines need a number (the evaluation pass rate, and how many days of backlog a queue
may carry). Both are in `config/rollout.yaml`, so changing a bar is a reviewed change.

The same file writes the weekly review notes: one row per week from the operational
store, with a note produced by a rule. A rule cannot flatter, and the same data always
gives the same note.

## Consequences

- The consent line checks the outcome, not the code: it looks for the thing that must
  never happen in the touches that were really delivered. The unit tests check the code.
- A check that fails names what is wrong ("Scaled CS team: 45 open, 12 a day").
- The lines of the plan that need a person's judgement (a spec signed off, the staff
  trained) stay in the document. The page does not pretend to answer them.
- Not a scheduled table (option 3): the page is fast enough, and one fewer table to keep
  current. Revisit if readiness has to be reported over time.

## Revisit if

Readiness needs a history (who was ready when), or a play needs its own bars instead of
the pilot's.
