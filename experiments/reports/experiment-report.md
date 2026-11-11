# Experiment report: plays against their holdouts

Synthetic data, fictional company. Written by `uv run python run.py experiments`.

As of 2026-10-09 (simulated calendar). Pilot segment: uncovered. Accounts count once they have been observed for 7 days or more.

> This is a simulation. Customers react to touches according to the assumptions in
> `config/sim_effects.yaml`, so any lift below was put there by those assumptions.
> What this report demonstrates is the measurement: holdouts, a pre-declared metric,
> an interval, a check on the split, and a decision rule.

## Summary

| Play | Success metric | Treatment | Holdout | Lift (95% interval) | p | Verdict |
|---|---|---|---|---|---|---|
| Find the admin | valid_admin_restored | 75% (43/57) | none | n/a | n/a | Not an experiment (no holdout): 75% reached the goal. |
| Detractor save | retained_30d | 100% (25/25) | 100% (7/7) | +0% (+0% to +0%) | 1.000 | Too early: fewer than 20 accounts in a group. |
| Onboarding rescue | setup_completed | 32% (11/34) | 0% (0/43) | +32% (+17% to +48%) | 0.000 | Working: +32% on the success metric, unlikely to be chance (p = 0.000). |
| Usage recovery | usage_recovered | 14% (3/22) | 8% (1/12) | +5% (-16% to +27%) | 0.646 | Too early: fewer than 20 accounts in a group. |
| Edition upgrade | expanded_30d | 0% (0/4) | 0% (0/2) | +0% (+0% to +0%) | 1.000 | Too early: fewer than 20 accounts in a group. |
| Seat expansion | expanded_30d | 2% (1/64) | 14% (5/35) | -13% (-25% to -1%) | 0.011 | Harmful: -13% on the success metric (p = 0.011). |
| Cross-product (Docs) | docs_adopted | 0% (0/4) | 0% (0/3) | +0% (+0% to +0%) | 1.000 | Too early: fewer than 20 accounts in a group. |

## Recommended decisions

- **Find the admin**: Keep running; track the rate.
- **Detractor save**: Keep testing.
- **Onboarding rescue**: Scale: move to the next rollout stage or the next segment, and keep a holdout.
- **Usage recovery**: Keep testing.
- **Edition upgrade**: Keep the slice running.
- **Seat expansion**: Stop the play and review the journey.
- **Cross-product (Docs)**: Keep the slice running.

## Find the admin

Owner: CS Operations lead. Stage: full. Success metric: Account has an emailable admin within 30 days.

- Entered so far: 59 accounts (57 treatment and 0 holdout observed long enough; median 11 days observed).
- Result: Not an experiment (no holdout): 75% reached the goal.

By highest rung of the ladder reached (treatment):

| Rung | Accounts | Reached the goal | Rate |
|---|---|---|---|
| human | 57 | 43 | 75% |

By week of entry:

| Week starting | Treatment | Holdout |
|---|---|---|
| 2026-09-28 | 75% of 57 | none |

## Detractor save

Owner: Scaled CS team lead. Stage: full. Success metric: Account is still active 30 days after entering the play.

- Entered so far: 54 accounts (25 treatment and 7 holdout observed long enough; median 11 days observed).
- Result: Too early: fewer than 20 accounts in a group.
- Split check: 20% in holdout against 20% planned: as designed (p = 0.95).
- Guardrail, still a customer: 100% treatment, 100% holdout.
- Revenue retained: 100.0% of $64,016 (treatment), 100.0% of $17,491 (holdout).
- Expansion won in the window: $1,842 treatment ($74 per account), $0 holdout ($0 per account).

By highest rung of the ladder reached (treatment):

| Rung | Accounts | Reached the goal | Rate |
|---|---|---|---|
| human | 25 | 25 | 100% |

By week of entry:

| Week starting | Treatment | Holdout |
|---|---|---|
| 2026-09-28 | 100% of 25 | 100% of 7 |

## Onboarding rescue

Owner: Digital Success Portfolio Lead. Stage: full. Success metric: Prerequisite closure reaches 75% or more within 30 days.

- Entered so far: 89 accounts (34 treatment and 43 holdout observed long enough; median 11 days observed).
- Result: Working: +32% on the success metric, unlikely to be chance (p = 0.000).
- Split check: 53% in holdout against 50% planned: as designed (p = 0.60).
- Guardrail, still a customer: 100% treatment, 100% holdout.
- Revenue retained: 100.0% of $75,091 (treatment), 100.0% of $76,776 (holdout).
- Expansion won in the window: $0 treatment ($0 per account), $0 holdout ($0 per account).

By highest rung of the ladder reached (treatment):

| Rung | Accounts | Reached the goal | Rate |
|---|---|---|---|
| digital | 1 | 0 | 0% |
| human | 33 | 11 | 33% |

By week of entry:

| Week starting | Treatment | Holdout |
|---|---|---|
| 2026-09-28 | 32% of 34 | 0% of 43 |

## Usage recovery

Owner: Digital Success Portfolio Lead. Stage: full. Success metric: Monthly active users back to at least 90% of the pre-drop level within 30 days.

- Entered so far: 43 accounts (22 treatment and 12 holdout observed long enough; median 11 days observed).
- Result: Too early: fewer than 20 accounts in a group.
- Split check: 40% in holdout against 50% planned: as designed (p = 0.17).
- Guardrail, still a customer: 100% treatment, 100% holdout.
- Revenue retained: 100.0% of $40,793 (treatment), 100.0% of $17,733 (holdout).
- Expansion won in the window: $0 treatment ($0 per account), $0 holdout ($0 per account).

By highest rung of the ladder reached (treatment):

| Rung | Accounts | Reached the goal | Rate |
|---|---|---|---|
| digital | 18 | 3 | 17% |
| human | 2 | 0 | 0% |
| none | 2 | 0 | 0% |

By week of entry:

| Week starting | Treatment | Holdout |
|---|---|---|
| 2026-09-28 | 14% of 22 | 8% of 12 |

## Edition upgrade

Owner: Digital Success Portfolio Lead, with Sales. Stage: slice. Success metric: A closed-won expansion opportunity within 30 days.

- Entered so far: 6 accounts (4 treatment and 2 holdout observed long enough; median 11 days observed).
- Result: Too early: fewer than 20 accounts in a group.
- Split check: 33% in holdout against 50% planned: as designed (p = 0.41).
- Guardrail, still a customer: 100% treatment, 100% holdout.
- Revenue retained: 100.0% of $7,455 (treatment), 100.0% of $2,642 (holdout).
- Expansion won in the window: $0 treatment ($0 per account), $0 holdout ($0 per account).

By highest rung of the ladder reached (treatment):

| Rung | Accounts | Reached the goal | Rate |
|---|---|---|---|
| digital | 2 | 0 | 0% |
| human | 2 | 0 | 0% |

By week of entry:

| Week starting | Treatment | Holdout |
|---|---|---|
| 2026-09-28 | 0% of 4 | 0% of 2 |

## Seat expansion

Owner: Sales lead, with Digital Success. Stage: full. Success metric: A closed-won expansion opportunity within 30 days.

- Entered so far: 125 accounts (64 treatment and 35 holdout observed long enough; median 11 days observed).
- Result: Harmful: -13% on the success metric (p = 0.011).
- Split check: 40% in holdout against 50% planned: as designed (p = 0.03).
- Guardrail, still a customer: 100% treatment, 100% holdout.
- Revenue retained: 100.0% of $121,567 (treatment), 100.0% of $92,738 (holdout).
- Expansion won in the window: $239 treatment ($4 per account), $3,986 holdout ($114 per account).

By highest rung of the ladder reached (treatment):

| Rung | Accounts | Reached the goal | Rate |
|---|---|---|---|
| human | 64 | 1 | 2% |

By week of entry:

| Week starting | Treatment | Holdout |
|---|---|---|
| 2026-09-28 | 2% of 64 | 14% of 35 |

## Cross-product (Docs)

Owner: Digital Success Portfolio Lead. Stage: slice. Success metric: The account publishes its first doc within 30 days.

- Entered so far: 8 accounts (4 treatment and 3 holdout observed long enough; median 11 days observed).
- Result: Too early: fewer than 20 accounts in a group.
- Split check: 38% in holdout against 50% planned: as designed (p = 0.48).
- Guardrail, still a customer: 100% treatment, 100% holdout.
- Revenue retained: 100.0% of $21,220 (treatment), 100.0% of $5,517 (holdout).
- Expansion won in the window: $1,842 treatment ($460 per account), $585 holdout ($195 per account).

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
| Handoffs to people | 225 (9 open now) |
| SLA breach rate | 16% |
| Escalation conversion (closed with a good outcome) | 61% |
| Unnecessary handoffs ("the agent should have handled this") | 4% |
| Handoffs from the agent | 37 |
| Docs gap (agent handoffs because no article covered the question) | 0% |

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
