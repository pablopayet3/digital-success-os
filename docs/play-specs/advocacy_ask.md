# Play spec: Reference request

Synthetic data, fictional company. Generated from `config/plays.yaml`, `config/journeys.yaml` and `config/play_specs.yaml` by `uv run python run.py specs`. Do not edit by hand.

| | |
|---|---|
| Play id | `advocacy_ask` (version 1) |
| Owner | Scaled CS team lead |
| Objective | Ask happy, healthy customers to act as a reference, only when it is earned. |
| Priority | 8 of 8 (1 claims an account first) |
| Exclusive | Yes. An account is in one exclusive play at a time. |
| Rollout stage | Slice: 10% of eligible accounts, chosen by hash. |
| Holdout | 10% of eligible accounts |
| Re-entry | Not within 60 days of leaving the play |

## Trigger and threshold

An account becomes a candidate when any of these signals fires:

- `advocate_ready`: Latest NPS of 9 or 10 within 90 days, health band green, account at least 90 days old, no open high-priority ticket, and not flagged by the churn model.

## Audience

- Coverage tier: the pilot segments in `config/rollout.yaml`.
- Lifecycle stage: adopting, mature, expansion.

## Exclusions

- `already_in_this_play`: In this play now, or left it less than 60 days ago (cooldown).
- `renewal_in_negotiation`: An open renewal opportunity is in negotiation. Sales owns the conversation.
- `in_another_play`: Already in another exclusive play. One conversation at a time.
- `open_escalation`: A person is already working an open task on this account.
- `no_emailable_contact`: Nobody at the account we are allowed to email.

## The job

Ask a happy, healthy customer to act as a reference, once, and only when it has been earned. The system writes the request; a success manager approves it before it is sent. A rejected draft ends the play for that customer.

## Intervention ladder

| Rung | What happens | Move up when |
|---|---|---|
| digital | A reference request by email, drafted by the system and approved by a success manager before it is sent.
 | This play stays digital. A person approves every request, and nobody is chased after a request goes unanswered. |

## Journey steps

1. `reference_request`: Email, template `reference_request` (digital).
2. `wait_for_answer`: Wait 14 days.
3. `done`: Exit with reason `sequence_finished`.

## What the automation may use

- Latest NPS score and date
- health score and band
- open high-priority tickets
- churn model flag

## What it must never do

- Send the request without a person's approval.
- Chase a customer who does not answer.
- Ask a customer who is unhappy or at risk.

## When a person takes over

- Never. This play has no human rung.
- What comes back: the person's outcome decides whether the journey resumes, ends or passes to Sales (`config/routing.yaml`, `outcomes`).

## Guardrails from the engine (every play)

- Consent. Only contacts with a valid address who have not opted out are emailed. An opt-out in the mailbox takes effect the same day.
- Frequency cap. At most 2 automated touches per account in any 7 days, across all plays.
- Holdout. Assigned by a hash of the account id, the play and its version. A holdout account gets nothing from this play and is reserved for the measurement window.
- Audit. Every decision (entered, held out, excluded and why) is written to the audit log.
- Pause. A complaint or a missing admin pauses every play's emails for the account.

## Test cases

- tests/test_engine.py (the request waits as a draft until a person approves it; a rejected draft ends the play)

## Success metric

`advocate_responded`: The contact accepts the reference request (clicks "Yes") within 30 days.

Measured over 30 days from entry, treatment against holdout, with a confidence interval (`docs/metrics.md`). Decided before launch; changing it is a new play version.
