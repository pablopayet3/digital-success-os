-- Gold (building block): the daily account facts plus an explainable health score.
-- One row per account per day.
--
-- The score is a weighted average of five components, each from 0 to 100. Every
-- component is stored, so anyone can see WHY an account is red.
-- Weights and bands come from config/health.yaml. Definitions: docs/metrics.md

{% set weights = var('health_weights') %}
{% set bands = var('health_bands') %}

with base as (

    select * from {{ ref('int_account_daily_base') }}

),

components as (

    select
        *,

        -- Adoption: 60% share of assigned seats active this month, 40% setup completion.
        round(100 * (
            0.6 * least(1.0, mau_30d / greatest(seats_assigned, 1))
            + 0.4 * prerequisite_closure_pct
        ), 1) as health_adoption,

        -- Engagement: 70% email open rate (a 50% open rate scores full marks; neutral
        -- when we sent nothing), 30% admin logins (8 or more in 30 days scores full marks).
        round(100 * (
            0.7 * case
                when emails_sent_30d = 0 then 0.5
                else least(1.0, (emails_opened_30d / emails_sent_30d) / 0.5)
            end
            + 0.3 * least(1.0, admin_logins_30d / 8.0)
        ), 1) as health_engagement,

        -- Sentiment: the latest NPS answer on a 0 to 100 scale. Neutral (60) if never asked.
        cast(coalesce(latest_nps_score * 10, 60) as double) as health_sentiment,

        -- Support: starts at 100; each open high-priority ticket costs 25,
        -- each one opened in the last 30 days costs 10.
        cast(greatest(
            0, 100 - 25 * open_high_priority_tickets - 10 * high_priority_tickets_30d
        ) as double) as health_support,

        -- Commercial: 50% seat utilisation, 50% seat trend over 30 days.
        round(100 * (
            0.5 * seat_utilisation
            + 0.5 * case
                when seats_assigned_30d_ago is null then 0.6
                when seats_assigned > seats_assigned_30d_ago then 1.0
                when seats_assigned = seats_assigned_30d_ago then 0.6
                else 0.2
            end
        ), 1) as health_commercial

    from base

),

scored as (

    select
        *,
        round(
            {{ weights['adoption'] }} * health_adoption
            + {{ weights['engagement'] }} * health_engagement
            + {{ weights['sentiment'] }} * health_sentiment
            + {{ weights['support'] }} * health_support
            + {{ weights['commercial'] }} * health_commercial,
            1
        ) as health_score
    from components

)

select
    *,
    case
        when health_score >= {{ bands['green'] }} then 'green'
        when health_score >= {{ bands['yellow'] }} then 'yellow'
        else 'red'
    end as health_band
from scored
