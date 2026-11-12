# Experiment report: plays against their holdouts

Synthetic data, fictional company. Written by `uv run python run.py experiments`.

As of 2026-10-27 (simulated calendar). Pilot segment: uncovered. Accounts count once they have been observed for 7 days or more.

> This is a simulation. Customers react to touches according to the assumptions in
> `config/sim_effects.yaml`, so any lift below was put there by those assumptions.
> What this report demonstrates is the measurement: holdouts, a pre-declared metric,
> an interval, a check on the split, and a decision rule.

## Summary

| Play | Success metric | Treatment | Holdout | Lift (95% interval) | p | Verdict |
|---|---|---|---|---|---|---|
| Find the admin | valid_admin_restored | 69% (45/65) | none | n/a | n/a | Not an experiment (no holdout): 69% reached the goal. |
| Detractor save | retained_30d | 100% (52/52) | 100% (8/8) | +0% (+0% to +0%) | 1.000 | Too early: fewer than 20 accounts in a group. |
| Onboarding rescue | setup_completed | 41% (19/46) | 2% (1/55) | +39% (+25% to +54%) | 0.000 | Working: +39% on the success metric, unlikely to be chance (p = 0.000). |
| Usage recovery | usage_recovered | 32% (10/31) | 13% (3/23) | +19% (-2% to +41%) | 0.102 | No effect detected. This sample could only have shown a lift of about 26% or more. |
| Edition upgrade | expanded_30d | 17% (1/6) | 50% (1/2) | -33% (-109% to +42%) | 0.346 | Too early: fewer than 20 accounts in a group. |
| Seat expansion | expanded_30d | 19% (16/83) | 21% (12/57) | -2% (-15% to +12%) | 0.796 | No effect detected. This sample could only have shown a lift of about 20% or more. |
| Cross-product (Docs) | docs_adopted | 0% (0/4) | 0% (0/3) | +0% (+0% to +0%) | 1.000 | Too early: fewer than 20 accounts in a group. |

## Recommended decisions

- **Find the admin**: Keep running; track the rate.
- **Detractor save**: Keep testing.
- **Onboarding rescue**: Scale: move to the next rollout stage or the next segment, and keep a holdout.
- **Usage recovery**: Keep testing until the sample can detect the lift that would justify the play.
- **Edition upgrade**: Keep the slice running.
- **Seat expansion**: Keep testing until the sample can detect the lift that would justify the play.
- **Cross-product (Docs)**: Keep the slice running.

## Find the admin

Owner: CS Operations lead. Stage: full. Success metric: Account has an emailable admin within 30 days.

- Entered so far: 67 accounts (65 treatment and 0 holdout observed long enough; median 29 days observed).
- Result: Not an experiment (no holdout): 69% reached the goal.

By highest rung of the ladder reached (treatment):

| Rung | Accounts | Reached the goal | Rate |
|---|---|---|---|
| human | 65 | 45 | 69% |

By week of entry:

| Week starting | Treatment | Holdout |
|---|---|---|
| 2026-09-28 | 71% of 58 | none |
| 2026-10-05 | 0% of 1 | none |
| 2026-10-12 | 67% of 6 | none |

## Detractor save

Owner: Scaled CS team lead. Stage: full. Success metric: Account is still active 30 days after entering the play.

- Entered so far: 70 accounts (52 treatment and 8 holdout observed long enough; median 26 days observed).
- Result: Too early: fewer than 20 accounts in a group.
- Split check: 13% in holdout against 20% planned: as designed (p = 0.14).
- Guardrail, still a customer: 100% treatment, 100% holdout.
- Revenue retained: 100.0% of $139,932 (treatment), 100.0% of $13,358 (holdout).
- Expansion won in the window: $350 treatment ($7 per account), $0 holdout ($0 per account).

By highest rung of the ladder reached (treatment):

| Rung | Accounts | Reached the goal | Rate |
|---|---|---|---|
| human | 52 | 52 | 100% |

By week of entry:

| Week starting | Treatment | Holdout |
|---|---|---|
| 2026-09-28 | 100% of 30 | 100% of 6 |
| 2026-10-05 | 100% of 7 | none |
| 2026-10-12 | 100% of 14 | 100% of 2 |
| 2026-10-19 | 100% of 1 | none |

## Onboarding rescue

Owner: Digital Success Portfolio Lead. Stage: full. Success metric: Prerequisite closure reaches 75% or more within 30 days.

- Entered so far: 103 accounts (46 treatment and 55 holdout observed long enough; median 29 days observed).
- Result: Working: +39% on the success metric, unlikely to be chance (p = 0.000).
- Split check: 53% in holdout against 50% planned: as designed (p = 0.49).
- Guardrail, still a customer: 96% treatment, 98% holdout.
- Revenue retained: 94.6% of $71,897 (treatment), 98.8% of $106,491 (holdout).
- Expansion won in the window: $0 treatment ($0 per account), $665 holdout ($12 per account).

By highest rung of the ladder reached (treatment):

| Rung | Accounts | Reached the goal | Rate |
|---|---|---|---|
| digital | 4 | 2 | 50% |
| agentic | 9 | 1 | 11% |
| human | 33 | 16 | 48% |

By week of entry:

| Week starting | Treatment | Holdout |
|---|---|---|
| 2026-09-28 | 50% of 36 | 0% of 45 |
| 2026-10-05 | 17% of 6 | 14% of 7 |
| 2026-10-12 | 0% of 3 | 0% of 3 |
| 2026-10-19 | 0% of 1 | none |

## Usage recovery

Owner: Digital Success Portfolio Lead. Stage: full. Success metric: Monthly active users back to at least 90% of the pre-drop level within 30 days.

- Entered so far: 60 accounts (31 treatment and 23 holdout observed long enough; median 26 days observed).
- Result: No effect detected. This sample could only have shown a lift of about 26% or more.
- Split check: 43% in holdout against 50% planned: as designed (p = 0.30).
- Guardrail, still a customer: 94% treatment, 96% holdout.
- Revenue retained: 83.8% of $56,815 (treatment), 96.0% of $43,758 (holdout).
- Expansion won in the window: $0 treatment ($0 per account), $488 holdout ($21 per account).

By highest rung of the ladder reached (treatment):

| Rung | Accounts | Reached the goal | Rate |
|---|---|---|---|
| digital | 23 | 8 | 35% |
| human | 7 | 2 | 29% |
| none | 1 | 0 | 0% |

By week of entry:

| Week starting | Treatment | Holdout |
|---|---|---|
| 2026-09-28 | 32% of 25 | 15% of 13 |
| 2026-10-05 | 50% of 4 | 0% of 6 |
| 2026-10-12 | 0% of 2 | 25% of 4 |

## Edition upgrade

Owner: Digital Success Portfolio Lead, with Sales. Stage: slice. Success metric: A closed-won expansion opportunity within 30 days.

- Entered so far: 9 accounts (6 treatment and 2 holdout observed long enough; median 28 days observed).
- Result: Too early: fewer than 20 accounts in a group.
- Split check: 33% in holdout against 50% planned: as designed (p = 0.32).
- Guardrail, still a customer: 83% treatment, 100% holdout.
- Revenue retained: 85.8% of $16,569 (treatment), 100.0% of $4,448 (holdout).
- Expansion won in the window: $1,096 treatment ($183 per account), $1,806 holdout ($903 per account).

By highest rung of the ladder reached (treatment):

| Rung | Accounts | Reached the goal | Rate |
|---|---|---|---|
| digital | 4 | 0 | 0% |
| human | 1 | 1 | 100% |
| none | 1 | 0 | 0% |

By week of entry:

| Week starting | Treatment | Holdout |
|---|---|---|
| 2026-09-28 | 20% of 5 | 50% of 2 |
| 2026-10-05 | 0% of 1 | none |

## Seat expansion

Owner: Sales lead, with Digital Success. Stage: full. Success metric: A closed-won expansion opportunity within 30 days.

- Entered so far: 148 accounts (83 treatment and 57 holdout observed long enough; median 29 days observed).
- Result: No effect detected. This sample could only have shown a lift of about 20% or more.
- Split check: 39% in holdout against 50% planned: uneven, but within what chance allows for a hash split. Watch it (p = 0.01).
- Guardrail, still a customer: 96% treatment, 96% holdout.
- Revenue retained: 92.8% of $177,530 (treatment), 91.9% of $137,081 (holdout).
- Expansion won in the window: $24,351 treatment ($293 per account), $14,790 holdout ($259 per account).

By highest rung of the ladder reached (treatment):

| Rung | Accounts | Reached the goal | Rate |
|---|---|---|---|
| human | 83 | 16 | 19% |

By week of entry:

| Week starting | Treatment | Holdout |
|---|---|---|
| 2026-09-28 | 23% of 64 | 25% of 36 |
| 2026-10-05 | 0% of 7 | 17% of 12 |
| 2026-10-12 | 9% of 11 | 0% of 5 |
| 2026-10-19 | 0% of 1 | 25% of 4 |

## Cross-product (Docs)

Owner: Digital Success Portfolio Lead. Stage: slice. Success metric: The account publishes its first doc within 30 days.

- Entered so far: 7 accounts (4 treatment and 3 holdout observed long enough; median 29 days observed).
- Result: Too early: fewer than 20 accounts in a group.
- Split check: 43% in holdout against 50% planned: as designed (p = 0.71).
- Guardrail, still a customer: 100% treatment, 100% holdout.
- Revenue retained: 100.0% of $18,387 (treatment), 100.0% of $4,932 (holdout).
- Expansion won in the window: $350 treatment ($88 per account), $0 holdout ($0 per account).

By highest rung of the ladder reached (treatment):

| Rung | Accounts | Reached the goal | Rate |
|---|---|---|---|
| digital | 4 | 0 | 0% |

By week of entry:

| Week starting | Treatment | Holdout |
|---|---|---|
| 2026-09-28 | 0% of 4 | 0% of 3 |

## Human fallback

| Metric | Value |
|---|---|
| Handoffs to people | 372 (6 open now) |
| SLA breach rate | 23% |
| Escalation conversion (closed with a good outcome) | 62% |
| Unnecessary handoffs ("the agent should have handled this") | 3% |
| Handoffs from the agent | 13 |
| Docs gap (agent handoffs because no article covered the question) | 8% |

## How to read this

- **Lift** is the treatment rate minus the holdout rate, in percentage points.
- **The interval** is where the true lift plausibly lies. If it includes zero, the
  play may have done nothing.
- **p** is how often a gap this large would appear if the play did nothing. Below
  0.05 is the bar for "working".
- **Split check**: assignment is by hash, so the holdout share should match the
  design. If it does not, something is filtering one group and the comparison is void.
- **By rung**: accounts that needed a person are the harder cases. A lower rate on
  the human rung does not mean people perform worse.
- Thirty days cannot show churn. Plays are judged on leading indicators (setup
  finished, usage recovered); retention is watched as a guardrail.
