# Metric definitions

Synthetic data, fictional company. One definition per metric, with its formula, grain,
owner and source table. If two dashboards disagree, this file decides.

Sections on agent, handoff and experiment metrics are added in the phases that build them.

## Lifecycle stage

Grain: one value per account per day. Source: `gold.account_daily.lifecycle_stage`
(`dbt/models/marts/account_daily.sql`). Owner: Digital Success Portfolio Lead.

The rules are checked in this order and **the first match wins**.

| Order | Stage | Rule | Why it sits here |
|---|---|---|---|
| 1 | `at_risk` | The churn model flags the account, **or** monthly active users have halved against the previous 30 days (and there were at least 3). | Most urgent. A new or renewing account that is collapsing is first of all at risk. |
| 2 | `renewal` | A paying account within 90 days of its contract anniversary. | A dated commercial event. Plays must behave differently near a renewal (for example, stay away during negotiation). |
| 3 | `onboarding` | Signed up less than 30 days ago, **or** fewer than 75% of setup steps are done. | An account that never finished setup is still onboarding, however old it is. |
| 4 | `expansion` | The expansion model flags the account, **or** 90% or more of seats are assigned. | Only healthy, set-up accounts reach this rule. |
| 5 | `mature` | At least 90 days old and half or more of the assigned seats active this month. | Settled and using the product. |
| 6 | `adopting` | Everything else. | Set up, not at risk, still building the habit. |

Why precedence matters: an account can satisfy several rules at once (a 20-day-old account
with a full seat count is both onboarding and a seat-expansion candidate). One stage per
account keeps audiences clean; the signals table still carries every signal that fires.

## Health score

Grain: one value per account per day. Source: `gold.account_daily` (`health_score`,
`health_band` and the five `health_*` components), built in
`dbt/models/marts/int_account_daily_health.sql`. Weights and bands: `config/health.yaml`.
Owner: Digital Success Portfolio Lead, with CS Operations.

`health_score = 0.35 adoption + 0.15 engagement + 0.20 sentiment + 0.15 support + 0.15 commercial`

Each component runs from 0 to 100 and is stored, so the app can show why an account is red.

| Component | Weight | Formula | Reads |
|---|---|---|---|
| Adoption | 0.35 | 60% share of assigned seats active this month + 40% setup completion | `mau_30d`, `seats_assigned`, `prerequisite_closure_pct` |
| Engagement | 0.15 | 70% email open rate (50% opens = full marks; neutral if nothing was sent) + 30% admin logins (8 in 30 days = full marks) | `emails_opened_30d`, `emails_sent_30d`, `admin_logins_30d` |
| Sentiment | 0.20 | Latest NPS score × 10; 60 if never surveyed | `latest_nps_score` |
| Support | 0.15 | 100 − 25 per open high-priority ticket − 10 per high-priority ticket in 30 days, not below 0 | `open_high_priority_tickets`, `high_priority_tickets_30d` |
| Commercial | 0.15 | 50% seat utilisation + 50% seat trend (growing 1.0, flat 0.6, shrinking 0.2) | `seat_utilisation`, `seats_assigned_30d_ago` |

Bands: green at 70 or above, yellow from 50, red below 50.

The health score is a description a person can read and argue with. It is not the churn
model. The model learns its own weights from outcomes; the health score uses weights the
business chose. Showing both, and where they disagree, is more useful than either alone.

## Signals

Grain: one row per account, per day, per signal firing. Source: `gold.signals`.
Owner: Digital Success Portfolio Lead. Every signal carries the number that fired it and
the evidence in words.

| Signal | Rule |
|---|---|
| `activation_stalled` | Account is at least 7 days old and fewer than 50% of setup steps are done |
| `usage_drop` | Monthly active users down 30% or more against the previous 30 days (at least 3 before) |
| `seat_pressure` | 90% or more of licensed seats are assigned |
| `edition_fit` | Not on the top edition, and at the automation-rule limit, at the integration limit, or using 90% or more of included Assist credits |
| `cross_product` | Does not own Relay Docs and created 3 or more document-style boards in 60 days |
| `detractor` | An NPS score of 6 or lower in the last 14 days |
| `support_friction` | 3 or more high-priority tickets in 30 days |
| `no_valid_admin` | No admin contact who has opted in and has a working email address |
| `churn_risk_high` | Churn score at or above the day's capacity cut-off |
| `expansion_ready` | Expansion score at or above the day's capacity cut-off |

## Core usage metrics

| Metric | Definition | Grain | Source | Owner |
|---|---|---|---|---|
| Active users (daily) | Different users with a `user_active` event on the day | account × day | `gold.fct_usage_daily.active_users` | Product Analytics |
| MAU | Different users active in the 30 days ending on the day | account × day | `gold.account_daily.mau_30d` | Product Analytics |
| Consumption | Relay Assist credits used in the 30 days ending on the day | account × day | `gold.account_daily.assist_credits_30d` | Product Analytics |
| Seat utilisation | Seats assigned ÷ seats licensed | account × day | `gold.account_daily.seat_utilisation` | RevOps |
| Prerequisite closure | Setup steps done ÷ 4 (first board, five users, first integration, SSO) | account × day | `gold.account_daily.prerequisite_closure_pct` | Digital Success |
| Churned within 90 days | The CRM recorded a churn date in the 90 days after the day | account × day | `gold.fct_outcome_labels` | RevOps |
| Expanded within 90 days | A closed-won expansion opportunity in the 90 days after the day | account × day | `gold.fct_outcome_labels` | RevOps |

"Today" always means the latest licence snapshot date in the warehouse, never the clock.

## Play outcomes (success metrics)

One row per enrolment in `gold.metrics_play_outcomes`, treatment and holdout alike. The
measurement window is the 30 days after the account entered the play
(`measurement_window_days` in `config/plays.yaml`). Each play names one of these as its
success metric before launch; the others are available as guardrails.

| Metric | Definition | Success metric of |
|---|---|---|
| `setup_completed` | Prerequisite closure reached 75% or more on any day in the window | Onboarding rescue |
| `usage_recovered` | Monthly active users reached 90% or more of the level before the drop (the prior-30-day figure on the day of entry) | Usage recovery |
| `retained_30d` | The account had not churned by the end of the window | Detractor save; guardrail for every play |
| `valid_admin_restored` | The account had an admin we may email on any day in the window | Find the admin |
| `expanded_30d` | An expansion opportunity was closed-won in the window | Seat expansion, Edition upgrade |
| `docs_adopted` | At least one doc was published in the window | Cross-product (Docs) |

Also on each row: `arr_at_entry`, `retained_arr` (ARR at entry if the account was
retained, else 0), `expansion_amount` (closed-won expansion in the window),
`highest_tier` (the highest ladder rung reached), `days_observed`, `window_complete`.

## Experiment results

Computed by `experiments/analyze.py` from the table above, per play version.

| Term | Definition |
|---|---|
| Treatment rate, holdout rate | Accounts that reached the success metric, divided by accounts in the group. Only accounts observed for 7 days or more count. |
| Lift | Treatment rate minus holdout rate, in percentage points. |
| 95% interval | Lift plus or minus 1.96 standard errors, each group using its own rate. |
| p-value | Two-sided two-proportion z-test with a pooled rate. Below 0.05 counts as a real difference. |
| Sample-ratio check | Chi-square test of the observed split against the designed holdout share. Below 0.001, the result is not read. Between 0.001 and 0.01 the report says the split is uneven. |
| Smallest detectable lift | The lift the sample would catch 80% of the time at the 5% level. |
| Retained ARR share | Sum of `retained_arr` divided by sum of `arr_at_entry`, per group. |
| Expansion per account | Sum of `expansion_amount` divided by accounts, per group. |
| Verdict | Working (p < 0.05, positive), Harmful (p < 0.05, negative), No effect detected, Too early (fewer than 20 accounts in a group), or Not an experiment (no holdout). |

## Human-fallback metrics

From `gold.metrics_handoffs` (one row per queue, reason and source).

| Metric | Definition |
|---|---|
| Handoff rate | Agent conversations that ended in a handoff, divided by all agent conversations (`gold.metrics_agent`) |
| Time to pickup | Days from task created to picked up |
| SLA breach rate | Tasks picked up after their due date, or still open past it, divided by all tasks |
| Escalation conversion | Tasks closed as resolved, saved or expansion opportunity, divided by tasks closed |
| Unnecessary handoff rate | Tasks closed as "the agent should have handled this", divided by tasks closed |
| Docs gap share | Agent handoffs with reason `not_in_docs`, divided by agent handoffs |

## Agent evaluation metrics

From `evals/reports/eval-report.md`.

| Metric | Definition |
|---|---|
| Pass rate | Cases where every code check passed (and the judge, where one applies), divided by cases run. Skipped cases are left out. |
| Judge score | 1 to 5 on grounding, answering the question, clarity and no promises. 4 or more passes. |
| Classifier accuracy | Replies whose predicted intent equals the simulator's label, divided by replies scored |
| Costly misses | Unsubscribes or complaints classified as anything else |
