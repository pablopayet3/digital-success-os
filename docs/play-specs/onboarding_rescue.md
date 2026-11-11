# Play spec: Onboarding rescue

Synthetic data, fictional company. Generated from `config/plays.yaml`, `config/journeys.yaml` and `config/play_specs.yaml` by `uv run python run.py specs`. Do not edit by hand.

| | |
|---|---|
| Play id | `onboarding_rescue` (version 1) |
| Owner | Digital Success Portfolio Lead |
| Objective | Get stalled accounts through setup (board, five users, integration, SSO). |
| Priority | 3 of 7 (1 claims an account first) |
| Exclusive | Yes. An account is in one exclusive play at a time. |
| Rollout stage | Full test: every eligible account, split into treatment and holdout. |
| Holdout | 50% of eligible accounts |
| Re-entry | Not within 60 days of leaving the play |

## Trigger and threshold

An account becomes a candidate when any of these signals fires:

- `activation_stalled`: Account is 7 or more days old and fewer than 50% of setup steps are done.

## Audience

- Coverage tier: the pilot segments in `config/rollout.yaml`.
- Lifecycle stage: onboarding, at_risk.

## Exclusions

- `already_in_this_play`: In this play now, or left it less than 60 days ago (cooldown).
- `in_another_play`: Already in another exclusive play. One conversation at a time.
- `open_escalation`: A person is already working an open task on this account.
- `no_emailable_admin`: No admin we are allowed to email. The "Find the admin" play handles it first.

## The job

Get a stalled account through setup. First the setup guide for the steps still missing. Then the onboarding agent offers a conversation and answers how-to questions from the help centre. Then a person.

## Intervention ladder

| Rung | What happens | Move up when |
|---|---|---|
| digital | Email with the setup guide for the steps still missing. | Still stalled 3 days after the email. |
| agentic | The onboarding agent offers the admin a conversation to finish setup. | The agent escalates (asked for a person, pricing or contract question, frustration, no answer in the docs, a tool failed), or the account is still stalled 4 days later. |
| human | CTA to the pooled CS team with what was tried and what is still missing. | Last rung. |

## Journey steps

1. `setup_guide`: Email, template `setup_guide` (digital).
2. `wait_for_progress`: Wait 3 days.
3. `still_stalled`: If `signal:activation_stalled` go to `agent_help`, otherwise `progressing`.
4. `agent_help`: The onboarding agent offers a conversation (agentic).
5. `wait_after_agent`: Wait 4 days.
6. `stalled_after_agent`: If `signal:activation_stalled` go to `csm_handoff`, otherwise `progressing`.
7. `csm_handoff`: Task for a person in queue `pooled_csm`, priority normal, reason `onboarding_stalled`. The journey waits for the outcome.
8. `progressing`: Exit with reason `no_longer_stalled`.

Goal (ends the journey at once when reached): `prerequisite_closure_pct >= 0.75`.

## What the automation may use

- The agent's tools: setup status (the four steps), account context (edition, seats, health band), help-centre search.
- The tools are bound to the one account in the conversation. They take no account id.

## What it must never do

- Quote a price, discuss a contract, a refund or a legal matter.
- Answer a product question that no help article covers.
- Promise a date, a discount or a feature.

## When a person takes over

- Step `csm_handoff`: Onboarding stalled after email and agent. Queue `pooled_csm` (SLA 48 hours). Next step for the person: Call the admin; walk through the missing setup steps.
- During an agent conversation, the hard rules in `agents/escalation.py` hand off at once: the customer asks for a person; frustration; pricing or upgrade (to Sales); contract, refund or legal; no help article covers the question; a tool fails; the same question twice; the model is unavailable. See `docs/human-fallback.md`.
- What comes back: the person's outcome decides whether the journey resumes, ends or passes to Sales (`config/routing.yaml`, `outcomes`).

## Guardrails from the engine (every play)

- Consent. Only contacts with a valid address who have not opted out are emailed. An opt-out in the mailbox takes effect the same day.
- Frequency cap. At most 2 automated touches per account in any 7 days, across all plays.
- Holdout. Assigned by a hash of the account id, the play and its version. A holdout account gets nothing from this play and is reserved for the measurement window.
- Audit. Every decision (entered, held out, excluded and why) is written to the audit log.
- Pause. A complaint or a missing admin pauses every play's emails for the account.

## Test cases

- evals/cases/onboarding_agent.yaml: every case with play onboarding_rescue
- tests/test_agents.py (each hard escalation rule; a pricing message never reaches the agent model)

## Success metric

`setup_completed`: Prerequisite closure reaches 75% or more within 30 days.

Measured over 30 days from entry, treatment against holdout, with a confidence interval (`docs/metrics.md`). Decided before launch; changing it is a new play version.
