# Play spec: Usage recovery

Synthetic data, fictional company. Generated from `config/plays.yaml`, `config/journeys.yaml` and `config/play_specs.yaml` by `uv run python run.py specs`. Do not edit by hand.

| | |
|---|---|
| Play id | `usage_recovery` (version 1) |
| Owner | Digital Success Portfolio Lead |
| Objective | Reverse a drop in usage before it becomes churn. |
| Priority | 4 of 7 (1 claims an account first) |
| Exclusive | Yes. An account is in one exclusive play at a time. |
| Rollout stage | Full test: every eligible account, split into treatment and holdout. |
| Holdout | 50% of eligible accounts |
| Re-entry | Not within 60 days of leaving the play |

## Trigger and threshold

An account becomes a candidate when any of these signals fires:

- `usage_drop`: Monthly active users are down 30% or more on the previous 30 days (at least 3 users before).

## Audience

- Coverage tier: the pilot segments in `config/rollout.yaml`.
- Lifecycle stage: adopting, mature, at_risk, expansion, renewal.

## Exclusions

- `already_in_this_play`: In this play now, or left it less than 60 days ago (cooldown).
- `renewal_in_negotiation`: An open renewal opportunity is in negotiation. Sales owns the conversation.
- `in_another_play`: Already in another exclusive play. One conversation at a time.
- `open_escalation`: A person is already working an open task on this account.

## The job

Remind an account whose usage is falling of what it is not using, twice, digitally. If sentiment is already negative, or usage is still falling 12 days later, a person takes over with the trend and the context.

## Intervention ladder

| Rung | What happens | Move up when |
|---|---|---|
| digital | Re-engagement email, then an in-app nudge. | Skip this tier when sentiment is already negative (a detractor score or support friction): go straight to a human. |
| human | CTA to the pooled CS team with usage trend, sentiment and tickets. | Usage is still falling 12 days after the first email. |

## Journey steps

1. `check_sentiment`: If `negative_sentiment` go to `csm_handoff`, otherwise `whats_new`.
2. `whats_new`: Email, template `usage_reengagement` (digital).
3. `wait_5`: Wait 5 days.
4. `nudge`: In-app prompt, template `usage_nudge` (digital).
5. `wait_7`: Wait 7 days.
6. `still_dropping`: If `signal:usage_drop` go to `csm_handoff`, otherwise `recovered`.
7. `csm_handoff`: Task for a person in queue `pooled_csm`, priority high, reason `usage_drop_needs_human`. The journey waits for the outcome.
8. `recovered`: Exit with reason `usage_recovered`.

Goal (ends the journey at once when reached): `signal usage_drop no longer fires`.

## What the automation may use

- Usage trend (monthly active users)
- features used
- NPS band
- high-priority tickets

## What it must never do

- Email an account whose sentiment is negative. It goes straight to a person.

## When a person takes over

- Step `csm_handoff`: Usage is falling and digital touches have not helped. Queue `pooled_csm` (SLA 48 hours). Next step for the person: Find out what changed (champion left, reorganisation, competitor trial).
- What comes back: the person's outcome decides whether the journey resumes, ends or passes to Sales (`config/routing.yaml`, `outcomes`).

## Guardrails from the engine (every play)

- Consent. Only contacts with a valid address who have not opted out are emailed. An opt-out in the mailbox takes effect the same day.
- Frequency cap. At most 2 automated touches per account in any 7 days, across all plays.
- Holdout. Assigned by a hash of the account id, the play and its version. A holdout account gets nothing from this play and is reserved for the measurement window.
- Audit. Every decision (entered, held out, excluded and why) is written to the audit log.
- Pause. A complaint or a missing admin pauses every play's emails for the account.

## Test cases

- tests/test_engine.py (branch on negative sentiment; the journey waits for the outcome)

## Success metric

`usage_recovered`: Monthly active users back to at least 90% of the pre-drop level within 30 days.

Measured over 30 days from entry, treatment against holdout, with a confidence interval (`docs/metrics.md`). Decided before launch; changing it is a new play version.
