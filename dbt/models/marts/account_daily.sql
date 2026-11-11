-- Gold: THE production table. One row per account per day.
-- Everything downstream (signals, the rules engine, the agents, the app) reads
-- accounts from here and nowhere else.
--
-- Contract: contracts/account_daily.yaml (owner, grain, columns, freshness, change policy).
--
-- Built from the daily facts and health score, plus the model scores written by
-- analytics/score.py, plus the lifecycle stage. The lifecycle rules are checked in
-- order and the first match wins (precedence explained in docs/metrics.md).

{{ config(tags=['scored']) }}

with health as (

    select * from {{ ref('int_account_daily_health') }}

),

scores as (

    select * from {{ source('analytics', 'account_scores') }}

)

select
    health.*,

    -- model scores (empty until the models have been trained)
    scores.churn_risk_score,
    coalesce(scores.churn_risk_high, false) as churn_risk_high,
    scores.churn_top_reasons,
    scores.expansion_score,
    coalesce(scores.expansion_ready, false) as expansion_ready,
    scores.expansion_top_reasons,

    case
        -- 1. most urgent first: the model says high risk, or usage has halved
        when coalesce(scores.churn_risk_high, false)
            or (health.mau_prior_30d >= 3 and health.mau_30d <= 0.5 * health.mau_prior_30d)
            then 'at_risk'
        -- 2. a paying account inside its 90-day renewal window
        when health.arr > 0 and health.days_to_renewal <= 90
            then 'renewal'
        -- 3. new, or setup never finished
        when health.account_age_days < 30 or health.prerequisite_closure_pct < 0.75
            then 'onboarding'
        -- 4. ready to grow: the model says so, or nearly every seat is taken
        when coalesce(scores.expansion_ready, false) or health.seat_utilisation >= 0.9
            then 'expansion'
        -- 5. settled: at least 90 days old and half the seats active
        when health.account_age_days >= 90 and health.mau_30d >= 0.5 * health.seats_assigned
            then 'mature'
        -- 6. everyone else is still building the habit
        else 'adopting'
    end as lifecycle_stage

from health
left join scores
    on health.account_id = scores.account_id
    and health.snapshot_date = scores.snapshot_date
