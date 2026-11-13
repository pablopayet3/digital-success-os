# Play spec: Seat expansion

Synthetic data, fictional company. Generated from `config/plays.yaml`, `config/journeys.yaml` and `config/play_specs.yaml` by `uv run python run.py specs`. Do not edit by hand.

| | |
|---|---|
| Play id | `expansion_seats` (version 1) |
| Owner | Sales lead, with Digital Success |
| Objective | Give account owners a ready brief when an account is running out of seats. |
| Priority | 6 of 8 (1 claims an account first) |
| Exclusive | No. It may run alongside another play. |
| Rollout stage | Full test: every eligible account, split into treatment and holdout. |
| Holdout | 50% of eligible accounts |
| Re-entry | Not within 60 days of leaving the play |

## Trigger and threshold

An account becomes a candidate when any of these signals fires:

- `seat_pressure`: 90% or more of licensed seats are assigned.
- `expansion_ready`: The expansion model's score is above today's capacity cut-off (top 60 accounts in the pilot segment).

## Audience

- Coverage tier: the pilot segments in `config/rollout.yaml`.
- Lifecycle stage: adopting, mature, expansion, renewal, onboarding.

## Exclusions

- `already_in_this_play`: In this play now, or left it less than 60 days ago (cooldown).
- `renewal_in_negotiation`: An open renewal opportunity is in negotiation. Sales owns the conversation.
- `open_escalation`: A person is already working an open task on this account.

## The job

Hand the account owner a brief when an account is running out of seats: the signal, the evidence, the likely need, a suggested opener and the risks. AI drafts; a person decides whether and how to reach out.

## Intervention ladder

| Rung | What happens | Move up when |
|---|---|---|
| agentic | An AI-written brief for the account owner, grounded in the account's data. | The brief always goes to a person. AI drafts, a human sells. |
| human | Sales CTA. The account owner decides whether and how to reach out. | Last rung. |

## Journey steps

1. `sales_brief`: Task for a person in queue `sales`, priority normal, reason `expansion_signal`. With an account brief. The journey waits for the outcome.

## What the automation may use

- Seats licensed and assigned
- usage trend
- expansion score and its reasons
- renewal date
- open tickets
- NPS band

## What it must never do

- Contact the customer.
- Put a number in the brief that is not in the account's data (checked by code; the brief falls back to a template if it does).

## When a person takes over

- Step `sales_brief`: Account is running out of seats. Queue `sales` (SLA 72 hours). Next step for the person: Review the brief and decide whether to reach out about more seats.
- What comes back: the person's outcome decides whether the journey resumes, ends or passes to Sales (`config/routing.yaml`, `outcomes`).

## Guardrails from the engine (every play)

- Consent. Only contacts with a valid address who have not opted out are emailed. An opt-out in the mailbox takes effect the same day.
- Frequency cap. At most 2 automated touches per account in any 7 days, across all plays.
- Holdout. Assigned by a hash of the account id, the play and its version. A holdout account gets nothing from this play and is reserved for the measurement window.
- Audit. Every decision (entered, held out, excluded and why) is written to the audit log.
- Pause. A complaint or a missing admin pauses every play's emails for the account.

## Test cases

- evals/cases/briefs.yaml: every case
- tests/test_agents.py (a brief with an invented number is replaced by the template)

## Success metric

`expanded_30d`: A closed-won expansion opportunity within 30 days.

Measured over 30 days from entry, treatment against holdout, with a confidence interval (`docs/metrics.md`). Decided before launch; changing it is a new play version.
