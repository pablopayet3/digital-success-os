# Play spec: Detractor save

Synthetic data, fictional company. Generated from `config/plays.yaml`, `config/journeys.yaml` and `config/play_specs.yaml` by `uv run python run.py specs`. Do not edit by hand.

| | |
|---|---|
| Play id | `detractor_save` (version 1) |
| Owner | Scaled CS team lead |
| Objective | Talk to an unhappy customer within 48 hours, with full context. |
| Priority | 2 of 7 (1 claims an account first) |
| Exclusive | Yes. An account is in one exclusive play at a time. |
| Rollout stage | Full test: every eligible account, split into treatment and holdout. |
| Holdout | 20% of eligible accounts |
| Re-entry | Not within 60 days of leaving the play |

## Trigger and threshold

An account becomes a candidate when any of these signals fires:

- `detractor`: An NPS score of 6 or lower in the last 14 days.

## Audience

- Coverage tier: the pilot segments in `config/rollout.yaml`.
- Lifecycle stage: any.

## Exclusions

- `already_in_this_play`: In this play now, or left it less than 60 days ago (cooldown).
- `renewal_in_negotiation`: An open renewal opportunity is in negotiation. Sales owns the conversation.
- `in_another_play`: Already in another exclusive play. One conversation at a time.

## The job

Put the unhappy customer in front of a person within 48 hours. The task carries the score, the comment in the customer's own words, usage trend and open tickets.

## Intervention ladder

| Rung | What happens | Move up when |
|---|---|---|
| human | CTA to the pooled CS team with the NPS comment, usage and open tickets. | Straight to a human. A detractor should not get an automated reply. |

## Journey steps

1. `csm_handoff`: Task for a person in queue `pooled_csm`, priority high, reason `detractor`. The journey waits for the outcome.

## What the automation may use

- NPS score and comment
- usage trend
- open tickets
- health score and components

## What it must never do

- Send an automated reply to a detractor.
- Let the agent talk to the customer.

## When a person takes over

- Step `csm_handoff`: Detractor NPS score. Queue `pooled_csm` (SLA 48 hours). Next step for the person: Call within 48 hours. Acknowledge the score, ask what went wrong.
- What comes back: the person's outcome decides whether the journey resumes, ends or passes to Sales (`config/routing.yaml`, `outcomes`).

## Guardrails from the engine (every play)

- Consent. Only contacts with a valid address who have not opted out are emailed. An opt-out in the mailbox takes effect the same day.
- Frequency cap. At most 2 automated touches per account in any 7 days, across all plays.
- Holdout. Assigned by a hash of the account id, the play and its version. A holdout account gets nothing from this play and is reserved for the measurement window.
- Audit. Every decision (entered, held out, excluded and why) is written to the audit log.
- Pause. A complaint or a missing admin pauses every play's emails for the account.

## Test cases

- tests/test_engine.py (the handoff packet carries the customer's quote)
- evals/cases/mailbox.yaml: complaint cases (same route, from the mailbox)

## Success metric

`retained_30d`: Account is still active 30 days after entering the play.

Measured over 30 days from entry, treatment against holdout, with a confidence interval (`docs/metrics.md`). Decided before launch; changing it is a new play version.
