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
| Find the admin | valid_admin_restored | 70% (47/67) | none | n/a | n/a | Not an experiment (no holdout): 70% reached the goal. |
| Detractor save | retained_30d | 100% (56/56) | 100% (12/12) | +0% (+0% to +0%) | 1.000 | Too early: fewer than 20 accounts in a group. |
| Onboarding rescue | setup_completed | 35% (17/49) | 0% (0/50) | +35% (+21% to +48%) | 0.000 | Working: +35% on the success metric, unlikely to be chance (p = 0.000). |
| Usage recovery | usage_recovered | 18% (6/34) | 15% (4/26) | +2% (-17% to +21%) | 0.816 | No effect detected. This sample could only have shown a lift of about 26% or more. |
| Edition upgrade | expanded_30d | 20% (1/5) | 0% (0/2) | +20% (-15% to +55%) | 0.495 | Too early: fewer than 20 accounts in a group. |
| Seat expansion | expanded_30d | 23% (20/86) | 10% (5/50) | +13% (+1% to +25%) | 0.054 | No effect detected. This sample could only have shown a lift of about 15% or more. |
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

- Entered so far: 68 accounts (67 treatment and 0 holdout observed long enough; median 29 days observed).
- Result: Not an experiment (no holdout): 70% reached the goal.

By highest rung of the ladder reached (treatment):

| Rung | Accounts | Reached the goal | Rate |
|---|---|---|---|
| human | 67 | 47 | 70% |

By week of entry:

| Week starting | Treatment | Holdout |
|---|---|---|
| 2026-09-28 | 69% of 59 | none |
| 2026-10-05 | 100% of 2 | none |
| 2026-10-12 | 67% of 6 | none |

## Detractor save

Owner: Scaled CS team lead. Stage: full. Success metric: Account is still active 30 days after entering the play.

- Entered so far: 72 accounts (56 treatment and 12 holdout observed long enough; median 24 days observed).
- Result: Too early: fewer than 20 accounts in a group.
- Split check: 19% in holdout against 20% planned: as designed (p = 0.91).
- Guardrail, still a customer: 100% treatment, 100% holdout.
- Revenue retained: 100.0% of $166,204 (treatment), 100.0% of $31,320 (holdout).
- Expansion won in the window: $873 treatment ($16 per account), $752 holdout ($63 per account).

By highest rung of the ladder reached (treatment):

| Rung | Accounts | Reached the goal | Rate |
|---|---|---|---|
| human | 56 | 56 | 100% |

By week of entry:

| Week starting | Treatment | Holdout |
|---|---|---|
| 2026-09-28 | 100% of 29 | 100% of 8 |
| 2026-10-05 | 100% of 5 | 100% of 2 |
| 2026-10-12 | 100% of 16 | 100% of 1 |
| 2026-10-19 | 100% of 6 | 100% of 1 |

## Onboarding rescue

Owner: Digital Success Portfolio Lead. Stage: full. Success metric: Prerequisite closure reaches 75% or more within 30 days.

- Entered so far: 100 accounts (49 treatment and 50 holdout observed long enough; median 29 days observed).
- Result: Working: +35% on the success metric, unlikely to be chance (p = 0.000).
- Split check: 50% in holdout against 50% planned: as designed (p = 1.00).
- Guardrail, still a customer: 98% treatment, 98% holdout.
- Revenue retained: 100.0% of $79,751 (treatment), 99.1% of $89,700 (holdout).
- Expansion won in the window: $0 treatment ($0 per account), $0 holdout ($0 per account).

By highest rung of the ladder reached (treatment):

| Rung | Accounts | Reached the goal | Rate |
|---|---|---|---|
| digital | 4 | 0 | 0% |
| agentic | 7 | 3 | 43% |
| human | 38 | 14 | 37% |

By week of entry:

| Week starting | Treatment | Holdout |
|---|---|---|
| 2026-09-28 | 43% of 37 | 0% of 44 |
| 2026-10-05 | 17% of 6 | 0% of 5 |
| 2026-10-12 | 0% of 3 | 0% of 1 |
| 2026-10-19 | 0% of 3 | none |

## Usage recovery

Owner: Digital Success Portfolio Lead. Stage: full. Success metric: Monthly active users back to at least 90% of the pre-drop level within 30 days.

- Entered so far: 72 accounts (34 treatment and 26 holdout observed long enough; median 25 days observed).
- Result: No effect detected. This sample could only have shown a lift of about 26% or more.
- Split check: 42% in holdout against 50% planned: as designed (p = 0.16).
- Guardrail, still a customer: 94% treatment, 92% holdout.
- Revenue retained: 92.3% of $64,255 (treatment), 92.9% of $49,290 (holdout).
- Expansion won in the window: $873 treatment ($26 per account), $1,497 holdout ($58 per account).

By highest rung of the ladder reached (treatment):

| Rung | Accounts | Reached the goal | Rate |
|---|---|---|---|
| digital | 18 | 3 | 17% |
| human | 14 | 3 | 21% |
| none | 2 | 0 | 0% |

By week of entry:

| Week starting | Treatment | Holdout |
|---|---|---|
| 2026-09-28 | 16% of 25 | 7% of 14 |
| 2026-10-05 | 40% of 5 | 29% of 7 |
| 2026-10-12 | 0% of 4 | 20% of 5 |

## Edition upgrade

Owner: Digital Success Portfolio Lead, with Sales. Stage: slice. Success metric: A closed-won expansion opportunity within 30 days.

- Entered so far: 8 accounts (5 treatment and 2 holdout observed long enough; median 29 days observed).
- Result: Too early: fewer than 20 accounts in a group.
- Split check: 38% in holdout against 50% planned: as designed (p = 0.48).
- Guardrail, still a customer: 100% treatment, 100% holdout.
- Revenue retained: 100.0% of $15,342 (treatment), 100.0% of $2,642 (holdout).
- Expansion won in the window: $1,436 treatment ($287 per account), $0 holdout ($0 per account).

By highest rung of the ladder reached (treatment):

| Rung | Accounts | Reached the goal | Rate |
|---|---|---|---|
| digital | 4 | 1 | 25% |
| human | 1 | 0 | 0% |

By week of entry:

| Week starting | Treatment | Holdout |
|---|---|---|
| 2026-09-28 | 25% of 4 | 0% of 2 |
| 2026-10-05 | 0% of 1 | none |

## Seat expansion

Owner: Sales lead, with Digital Success. Stage: full. Success metric: A closed-won expansion opportunity within 30 days.

- Entered so far: 149 accounts (86 treatment and 50 holdout observed long enough; median 29 days observed).
- Result: No effect detected. This sample could only have shown a lift of about 15% or more.
- Split check: 39% in holdout against 50% planned: uneven, but within what chance allows for a hash split. Watch it (p = 0.01).
- Guardrail, still a customer: 100% treatment, 98% holdout.
- Revenue retained: 100.0% of $189,280 (treatment), 98.8% of $126,487 (holdout).
- Expansion won in the window: $22,143 treatment ($257 per account), $6,071 holdout ($121 per account).

By highest rung of the ladder reached (treatment):

| Rung | Accounts | Reached the goal | Rate |
|---|---|---|---|
| human | 86 | 20 | 23% |

By week of entry:

| Week starting | Treatment | Holdout |
|---|---|---|
| 2026-09-28 | 26% of 66 | 11% of 35 |
| 2026-10-05 | 21% of 14 | 0% of 9 |
| 2026-10-12 | 0% of 4 | 17% of 6 |
| 2026-10-19 | 0% of 2 | none |

## Cross-product (Docs)

Owner: Digital Success Portfolio Lead. Stage: slice. Success metric: The account publishes its first doc within 30 days.

- Entered so far: 7 accounts (4 treatment and 3 holdout observed long enough; median 29 days observed).
- Result: Too early: fewer than 20 accounts in a group.
- Split check: 43% in holdout against 50% planned: as designed (p = 0.71).
- Guardrail, still a customer: 100% treatment, 100% holdout.
- Revenue retained: 100.0% of $18,037 (treatment), 100.0% of $4,932 (holdout).
- Expansion won in the window: $0 treatment ($0 per account), $0 holdout ($0 per account).

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
| Handoffs to people | 387 (5 open now) |
| SLA breach rate | 23% |
| Escalation conversion (closed with a good outcome) | 63% |
| Unnecessary handoffs ("the agent should have handled this") | 4% |
| Handoffs from the agent | 19 |
| Docs gap (agent handoffs because no article covered the question) | 47% |

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
