-- Gold: signals. One row per account, per day, per signal that is firing.
-- A signal is a plain rule on the production table. The rules engine (Phase 4)
-- reads this table and decides which play, if any, each account enters.
--
-- signal_value is the number that made the rule fire; evidence says it in words,
-- so a human or an agent can see why.

{{ config(tags=['scored']) }}

with accounts as (

    select * from {{ ref('account_daily') }}

)

-- Onboarding has stalled: a week in, fewer than half of the setup steps are done.
select
    snapshot_date,
    account_id,
    'activation_stalled' as signal_id,
    cast(prerequisite_closure_pct as double) as signal_value,
    'Day ' || {{ text('account_age_days') }} || ': '
        || {{ text('cast(round(100 * prerequisite_closure_pct) as integer)') }}
        || '% of setup steps done' as evidence
from accounts
where account_age_days >= 7 and prerequisite_closure_pct < 0.5

union all

-- Usage is falling: monthly active users down 30% or more on the previous 30 days.
select
    snapshot_date,
    account_id,
    'usage_drop',
    cast(round(1 - mau_30d / mau_prior_30d, 3) as double),
    'Monthly active users fell from ' || {{ text('mau_prior_30d') }}
        || ' to ' || {{ text('mau_30d') }}
from accounts
where mau_prior_30d >= 3 and mau_30d <= 0.7 * mau_prior_30d

union all

-- Nearly out of seats: 90% or more of licensed seats are assigned.
select
    snapshot_date,
    account_id,
    'seat_pressure',
    cast(seat_utilisation as double),
    {{ text('seats_assigned') }} || ' of ' || {{ text('seats_licensed') }} || ' seats assigned'
from accounts
where seat_utilisation >= 0.9

union all

-- Outgrowing the edition: at a limit that the next edition up would lift.
select
    snapshot_date,
    account_id,
    'edition_fit',
    cast(greatest(
        automation_rules_total / automation_rule_limit,
        integrations_total / integration_limit,
        case
            when has_assist and assist_credits_included > 0
                then assist_credits_30d / assist_credits_included
            else 0
        end
    ) as double),
    case
        when automation_rules_total >= automation_rule_limit
            then 'At the automation rule limit (' || {{ text('automation_rule_limit') }}
                || ') of ' || edition
        when integrations_total >= integration_limit
            then 'At the integration limit (' || {{ text('integration_limit') }}
                || ') of ' || edition
        else 'Used ' || {{ text('assist_credits_30d') }} || ' of '
            || {{ text('assist_credits_included') }} || ' included Assist credits in 30 days'
    end
from accounts
where edition <> 'enterprise'
  and (
      automation_rules_total >= automation_rule_limit
      or integrations_total >= integration_limit
      or (
          has_assist and assist_credits_included > 0
          and assist_credits_30d >= 0.9 * assist_credits_included
      )
  )

union all

-- Using boards as documents without owning Docs.
select
    snapshot_date,
    account_id,
    'cross_product',
    cast(doc_like_boards_60d as double),
    {{ text('doc_like_boards_60d') }}
        || ' document-style boards created in 60 days, no Relay Docs'
from accounts
where not has_docs and doc_like_boards_60d >= 3

union all

-- An unhappy answer: NPS of 6 or lower in the last 14 days.
select
    snapshot_date,
    account_id,
    'detractor',
    cast(lowest_nps_14d as double),
    'NPS score of ' || {{ text('lowest_nps_14d') }} || ' in the last 14 days'
from accounts
where lowest_nps_14d <= 6

union all

-- Support trouble: three or more high-priority tickets in 30 days.
select
    snapshot_date,
    account_id,
    'support_friction',
    cast(high_priority_tickets_30d as double),
    {{ text('high_priority_tickets_30d') }} || ' high-priority tickets in 30 days ('
        || {{ text('open_high_priority_tickets') }} || ' still open)'
from accounts
where high_priority_tickets_30d >= 3

union all

-- Nobody to talk to: no admin with a working address and consent.
select
    snapshot_date,
    account_id,
    'no_valid_admin',
    cast(emailable_contacts as double),
    'No admin we can email (' || {{ text('emailable_contacts') }}
        || ' other contacts can be emailed)'
from accounts
where not has_valid_admin

union all

-- The churn model's score is above today's capacity cut-off.
select
    snapshot_date,
    account_id,
    'churn_risk_high',
    churn_risk_score,
    'Churn risk ' || {{ text('cast(round(100 * churn_risk_score) as integer)') }} || '%: '
        || churn_top_reasons
from accounts
where churn_risk_high

union all

-- The expansion model's score is above today's capacity cut-off.
select
    snapshot_date,
    account_id,
    'expansion_ready',
    expansion_score,
    'Expansion likelihood ' || {{ text('cast(round(100 * expansion_score) as integer)') }}
        || '%: ' || expansion_top_reasons
from accounts
where expansion_ready
