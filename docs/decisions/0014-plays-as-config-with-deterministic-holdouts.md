# 0014: Plays as config, holdouts by hash, guardrails in code

Status: accepted (Phase 4). Synthetic data, fictional company.

## Context

Seven plays run on the same accounts. They compete for attention, they must respect
consent, and each has to be measurable. The people who own plays are not engineers, and
the people who audit them will ask "why did this account get that email?"

## Decisions

**1. Plays and journeys are config, not code.** `config/plays.yaml` holds the catalog
(trigger, audience, exclusions, intervention ladder, holdout, rollout stage, success
metric, owner, version). `config/journeys.yaml` holds the steps. `engine/catalog.py`
validates both at start-up and refuses to run a broken configuration. Changing a play is
an edit to a file, reviewed through change control, with no deployment.

**2. Holdout and rollout are decided by a hash, not a random draw.**
`hash(account, play, version)` places each account in treatment or holdout, and inside or
outside the 10% rollout slice (`engine/assignment.py`). The same account always gets the
same answer, on any machine, on any day. Nobody can nudge an account into treatment, and
re-running the engine never reshuffles groups. Raising the play's version reshuffles them
on purpose.

**3. A holdout is a real enrolment that receives nothing.** It is recorded as "would have
entered", keeps the account out of other exclusive plays for the measurement window (so
another play cannot contaminate the comparison), and is released afterwards.

**4. Priority resolves conflicts.** Plays are evaluated in priority order and an account
may be in one exclusive play at a time. Sales CTAs and the find-the-admin task are not
exclusive: they can sit alongside another play.

**5. Consent and frequency are enforced by the engine, not by each journey.** Before any
email the runner re-checks that the contact opted in and has a working address
(including opt-outs learned since the last CRM sync), that the account is not paused, and
that the contact has had fewer than two touches in the last seven days across all plays.
A touch that is not allowed today is deferred and the reason is logged.

**6. Every decision is logged with its reason.** The audit log records each entry, each
holdout and each exclusion in plain words.

**7. Every play declares its intervention ladder.** Digital, then agentic, then human, with
the rule for moving up a rung. Each step carries its tier, and each enrolment records the
highest tier it reached, so results can be reported per rung.

**8. Pilot holdouts are large.** 50% for most plays: a pilot exists to learn, and a small
holdout learns slowly. Two exceptions: 20% for the detractor play (withholding help from an
unhappy customer has a real cost) and 0% for find-the-admin (data hygiene, not an
experiment). After the pilot, plays that scale move to a 10% standing holdout.

## Consequences

- A play owner can read and change a play without reading code.
- "Why not?" always has an answer in the audit log.
- Holdouts cost something: half the eligible accounts get no help during the pilot. That
  is the price of knowing what a play moved.
- With one exclusive play per account, a lower-priority play can be starved by a
  higher-priority one. The audit log shows how often ("already in another play").

## Revisit if

Plays need to share an account (for example an expansion email during onboarding). Then
exclusivity becomes a per-pair rule rather than a global one.
