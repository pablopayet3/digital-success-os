# Play spec: Edition upgrade

Synthetic data, fictional company. Generated from `config/plays.yaml`, `config/journeys.yaml` and `config/play_specs.yaml` by `uv run python run.py specs`. Do not edit by hand.

| | |
|---|---|
| Play id | `edition_upgrade` (version 1) |
| Owner | Digital Success Portfolio Lead, with Sales |
| Objective | Help accounts that have outgrown their edition see the value of the next one. |
| Priority | 5 of 7 (1 claims an account first) |
| Exclusive | Yes. An account is in one exclusive play at a time. |
| Rollout stage | Slice: 10% of eligible accounts, chosen by hash. |
| Holdout | 50% of eligible accounts |
| Re-entry | Not within 60 days of leaving the play |

## Trigger and threshold

An account becomes a candidate when any of these signals fires:

- `edition_fit`: At the automation-rule or integration limit of the edition, or 90% of included Assist credits used in 30 days. Not for the top edition.

## Audience

- Coverage tier: the pilot segments in `config/rollout.yaml`.
- Lifecycle stage: adopting, mature, expansion.
- Edition: free, standard, premium.

## Exclusions

- `already_in_this_play`: In this play now, or left it less than 60 days ago (cooldown).
- `renewal_in_negotiation`: An open renewal opportunity is in negotiation. Sales owns the conversation.
- `in_another_play`: Already in another exclusive play. One conversation at a time.
- `open_escalation`: A person is already working an open task on this account.
- `no_emailable_contact`: Nobody at the account we are allowed to email.

## The job

Show an account at an edition limit what the next edition lifts, with its own numbers. A reply with a question is a buying signal and goes to Sales with a brief.

## Intervention ladder

| Rung | What happens | Move up when |
|---|---|---|
| digital | Value email showing the limit the account has reached and what lifts it. | The contact replies with a question. |
| agentic | The agent answers product questions from the docs. | Any pricing or buying question. Always a human. |
| human | Sales CTA for the account owner, with a brief. | Last rung. |

## Journey steps

1. `value_email`: Email, template `edition_value` (digital).
2. `wait_4`: Wait 4 days.
3. `replied`: If `contact_replied` go to `sales_handoff`, otherwise `nudge`.
4. `sales_handoff`: Task for a person in queue `sales`, priority normal, reason `buying_intent`. With an account brief. The journey waits for the outcome.
5. `nudge`: In-app prompt, template `edition_nudge` (digital).
6. `done`: Exit with reason `sequence_finished`.

## What the automation may use

- Edition and its limits
- automation rules and integrations in use
- Assist credits used

## What it must never do

- State a price. The email names the limit and what lifts it
- never what it costs.

## When a person takes over

- Step `sales_handoff`: Account at an edition limit replied to the value email. Queue `sales` (SLA 72 hours). Next step for the person: Follow up on the reply; the contact is asking about the next edition.
- What comes back: the person's outcome decides whether the journey resumes, ends or passes to Sales (`config/routing.yaml`, `outcomes`).

## Guardrails from the engine (every play)

- Consent. Only contacts with a valid address who have not opted out are emailed. An opt-out in the mailbox takes effect the same day.
- Frequency cap. At most 2 automated touches per account in any 7 days, across all plays.
- Holdout. Assigned by a hash of the account id, the play and its version. A holdout account gets nothing from this play and is reserved for the measurement window.
- Audit. Every decision (entered, held out, excluded and why) is written to the audit log.
- Pause. A complaint or a missing admin pauses every play's emails for the account.

## Test cases

- evals/cases/onboarding_agent.yaml: pricing and upgrade cases (always handed to Sales)
- evals/cases/mailbox.yaml: buying_intent cases
- `evals/cases/briefs.yaml` (1 cases): brf-02-at-the-rule-limit
- `evals/cases/mailbox.yaml` (1 cases): mbx-05-buying-outranks-question

## Success metric

`expanded_30d`: A closed-won expansion opportunity within 30 days.

Measured over 30 days from entry, treatment against holdout, with a confidence interval (`docs/metrics.md`). Decided before launch; changing it is a new play version.
