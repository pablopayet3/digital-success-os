# Product requirements: Digital Success OS

Synthetic data, fictional company (Lumen Labs sells Relay). Owner: Digital Success
Portfolio Lead.

## Problem

Lumen Labs has about 1,100 customers. Roughly a third have a named success manager.
The rest are **uncovered**: nobody watches whether they finish setup, whether usage is
falling, or whether they have outgrown their edition. The signals exist (telemetry, CRM,
tickets, NPS, email replies) but they sit in separate systems, nobody acts on them in
time, and when automation does reach a customer nobody can say whether it helped.

## Users

| User | What they need | What they get |
|---|---|---|
| Admin of an uncovered account | To finish setup and get answers without waiting for a person who is not assigned to them | Timely guidance, an agent that answers from the help centre, and a person when it matters |
| Pooled CSM | To spend time on the accounts where a person changes the outcome | A queue ordered by priority and SLA, each task with full context and a recommended next step |
| Account owner (Sales) | To know which accounts are ready to grow, with evidence | A brief with the signal, the numbers, a suggested opener and the risks |
| CS leadership | To know what the programme moved | Every play measured against a holdout, with a scale, fix or stop recommendation |
| Data and agent engineers | Clear requirements | A data requirements spec, a data contract, and one spec per play |

## Goals and how we will know

| Goal | Metric | Pilot target |
|---|---|---|
| Stalled accounts finish setup | Setup completed (75% of steps) within 30 days, treatment against holdout | A lift the pilot can detect (about 20 points with 40 accounts a side) |
| Falling usage is caught early | Usage recovered to 90% of the earlier level within 30 days, against holdout | Measured; too few accounts in 30 days for a target |
| Growth signals reach a seller with evidence | Expansion closed-won within 30 days, against holdout; expansion revenue per account | Positive and not explained by chance |
| People are used where they matter | Unnecessary-handoff rate; SLA breach rate | Under 10% unnecessary; under 15% breached |
| The agent is safe | Pass rate on hard-rule eval cases (pricing, contract, person, frustration) | 100%, on every prompt version |
| We do not annoy customers | Opt-outs; touches per account per week | Cap of 2 automated touches in 7 days, enforced |

## Scope

Eight plays (`config/plays.yaml`), each with a ladder of digital, agentic and human
steps; two agents (onboarding, mailbox triage); account briefs for Sales; a human console;
an experiment report and an agent evaluation report.

## Non-goals

- Replacing success managers on covered accounts. The pilot is the uncovered segment.
- Letting an agent quote prices, change a subscription, or discuss contracts.
- Sending real email. Journey emails are written to an outbox folder.
- A general chatbot. The agent answers setup questions from the help centre and hands
  off everything else.

## Risks

| Risk | What we do about it |
|---|---|
| Bad data triggers the wrong play | Validation at ingest, 100 data tests, a data contract, freshness checks. A play never runs on an account whose data failed. |
| The agent says something wrong or commits the company | Hard rules in code, answers only from retrieved articles, evals on every prompt version, handoff when unsure |
| Customers are over-contacted | Engine-level consent and frequency cap; one exclusive play at a time; complaints pause all emails |
| Queues overflow and SLAs slip | Flags by team capacity, not by score; capacity alerts per queue; a ladder that tries digital first |
| We cannot tell whether it worked | Holdouts by hash, a metric declared before launch, a sample-ratio check, and a written decision rule |
| No owner for a table, play or queue | The ownership map names a DRI for each, and lists the gaps |

## Rollout

Slice (10% of eligible accounts), then a full test with a 50% holdout on the uncovered
segment, a weekly review, and a scale, fix or stop decision per play after six to eight
weeks. Scaling to the pooled segment is one line of configuration. See `docs/pilot-plan.md`.