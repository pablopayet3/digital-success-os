# Play spec: Cross-product (Docs)

Synthetic data, fictional company. Generated from `config/plays.yaml`, `config/journeys.yaml` and `config/play_specs.yaml` by `uv run python run.py specs`. Do not edit by hand.

| | |
|---|---|
| Play id | `cross_product_docs` (version 1) |
| Owner | Digital Success Portfolio Lead |
| Objective | Show teams that use boards as documents what Relay Docs would give them. |
| Priority | 7 of 7 (1 claims an account first) |
| Exclusive | Yes. An account is in one exclusive play at a time. |
| Rollout stage | Slice: 10% of eligible accounts, chosen by hash. |
| Holdout | 50% of eligible accounts |
| Re-entry | Not within 60 days of leaving the play |

## Trigger and threshold

An account becomes a candidate when any of these signals fires:

- `cross_product`: 3 or more document-style boards created in 60 days, and the account does not own Relay Docs.

## Audience

- Coverage tier: the pilot segments in `config/rollout.yaml`.
- Lifecycle stage: adopting, mature, expansion.

## Exclusions

- `already_in_this_play`: In this play now, or left it less than 60 days ago (cooldown).
- `in_another_play`: Already in another exclusive play. One conversation at a time.
- `open_escalation`: A person is already working an open task on this account.
- `no_emailable_contact`: Nobody at the account we are allowed to email.

## The job

Show teams that write documents on boards what Relay Docs would give them: one in-app prompt and one email. Nobody is chased.

## Intervention ladder

| Rung | What happens | Move up when |
|---|---|---|
| digital | In-app prompt on board creation, plus one email. | This play stays digital. Adoption is tracked, nobody is chased. |

## Journey steps

1. `in_app_prompt`: In-app prompt, template `docs_prompt` (digital).
2. `docs_email`: Email, template `docs_intro` (digital).
3. `watch`: Wait 14 days.
4. `done`: Exit with reason `sequence_finished`.

Goal (ends the journey at once when reached): `docs_published_30d >= 1`.

## What the automation may use

- Document-style boards created in 60 days
- whether the account owns Relay Docs

## What it must never do

- Escalate to a person. This play stays digital.

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

- tests/test_engine.py (the frequency cap holds across plays)

## Success metric

`docs_adopted`: The account publishes its first doc within 30 days.

Measured over 30 days from entry, treatment against holdout, with a confidence interval (`docs/metrics.md`). Decided before launch; changing it is a new play version.
