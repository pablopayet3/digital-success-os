# Play spec: Find the admin

Synthetic data, fictional company. Generated from `config/plays.yaml`, `config/journeys.yaml` and `config/play_specs.yaml` by `uv run python run.py specs`. Do not edit by hand.

| | |
|---|---|
| Play id | `find_the_admin` (version 1) |
| Owner | CS Operations lead |
| Objective | Make sure every account has an admin we are allowed to email. |
| Priority | 1 of 7 (1 claims an account first) |
| Exclusive | No. It may run alongside another play. |
| Rollout stage | Full test: every eligible account, split into treatment and holdout. |
| Holdout | None. This play is data hygiene, not an experiment. |
| Re-entry | Not within 60 days of leaving the play |

## Trigger and threshold

An account becomes a candidate when any of these signals fires:

- `no_valid_admin`: No admin contact with a working email address and consent.

## Audience

- Coverage tier: the pilot segments in `config/rollout.yaml`.
- Lifecycle stage: any.

## Exclusions

- `already_in_this_play`: In this play now, or left it less than 60 days ago (cooldown).

## The job

Find a person. Open a research task for the contact-research queue with what we know about the account, and pause other plays' emails until an admin we may contact exists.

## Intervention ladder

| Rung | What happens | Move up when |
|---|---|---|
| human | Research task to identify the right admin and update the CRM. | This play starts at the human tier. There is nobody to email. |

## Journey steps

1. `research_task`: Task for a person in queue `admin_research`, priority low, reason `no_valid_admin`. The journey waits for the outcome.

Goal (ends the journey at once when reached): `has_valid_admin >= 1`.

## What the automation may use

- CRM contacts and their consent status
- product activity by user (who is active)

## What it must never do

- Email anyone at the account to ask who the admin is.

## When a person takes over

- Step `research_task`: No admin we can email. Queue `admin_research` (SLA 120 hours). Next step for the person: Identify the current admin, confirm consent, update the CRM.
- What comes back: the person's outcome decides whether the journey resumes, ends or passes to Sales (`config/routing.yaml`, `outcomes`).

## Guardrails from the engine (every play)

- Consent. Only contacts with a valid address who have not opted out are emailed. An opt-out in the mailbox takes effect the same day.
- Frequency cap. At most 2 automated touches per account in any 7 days, across all plays.
- Holdout. Assigned by a hash of the account id, the play and its version. A holdout account gets nothing from this play and is reserved for the measurement window.
- Audit. Every decision (entered, held out, excluded and why) is written to the audit log.
- Pause. A complaint or a missing admin pauses every play's emails for the account.

## Test cases

- tests/test_engine.py (plays enter the right accounts; a paused account gets no email)
- evals/cases/mailbox.yaml: left_company cases (a departed admin opens this task)

## Success metric

`valid_admin_restored`: Account has an emailable admin within 30 days.

Measured over 30 days from entry, treatment against holdout, with a confidence interval (`docs/metrics.md`). Decided before launch; changing it is a new play version.
