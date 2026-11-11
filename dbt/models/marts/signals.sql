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
    snapshot_date, account_id, 'activation_stalled' as signal_id,
    prerequisite_closure_pct as signal_value,
    'Day ' || account_age_days || ': ' || cast(round(100 * prerequisite_closure_pct) as integer)
        || '% of setup steps done' as evidence
from accounts
where account_age_days >= 7 and prerequisite_closure_pct < 0.5

union all

-- Usage is falling: monthly active users down 30% or more on the previous 30 days.
select
    snapshot_date, account_id, 'usage_drop',
    round(1 - mau_30d / mau_prior_30d, 3),
    'Monthly active users fell from ' || mau_prior_30d || ' to ' || mau_30d
from accounts
where mau_prior_30d >= 3 and mau_30d <= 0.7 * mau_prior_30d

union all

-- Nearly out of seats: 90% or more of licensed seats are assigned.
select
    snapshot_date, account_id, 'seat_pressure',
    seat_utilisation,
    seats_assigned || ' of ' || seats_licensed || ' seats assigned'
from accounts
where seat_utilisation >= 0.9

union all

-- Outgrowing the edition: at a limit that the next edition up would lift.
select
    snapshot_date, account_id, 'edition_fit',
    greatest(
        automation_rules_total / automation_rule_limit,
        integrations_total / integration_limit,
        case when has_assist and assist_credits_included > 0
            then assist_credits_30d / assist_credits_included else 0 end
    ),
    case
        when automation_rules_total >= automation_rule_limit
            then 'At the automation rule limit (' || automation_rule_limit || ') of ' || edition
        when integrations_total >= integration_limit
            then 'At the integration limit (' || integration_limit || ') of ' || edition
        else 'Used ' || assist_credits_30d || ' of ' || assist_credits_included
            || ' included Assist credits in 30 days'
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
    snapshot_date, account_id, 'cross_product',
    doc_like_boards_60d,
    doc_like_boards_60d || ' document-style boards created in 60 days, no Relay Docs'
from accounts
where not has_docs and doc_like_boards_60d >= 3

union all

-- An unhappy answer: NPS of 6 or lower in the last 14 days.
select
    snapshot_date, account_id, 'detractor',
    lowest_nps_14d,
    'NPS score of ' || lowest_nps_14d || ' in the last 14 days'
from accounts
where lowest_nps_14d <= 6

union all

-- Support trouble: three or more high-priority tickets in 30 days.
select
    snapshot_date, account_id, 'support_friction',
    high_priority_tickets_30d,
    high_priority_tickets_30d || ' high-priority tickets in 30 days ('
        || open_high_priority_tickets || ' still open)'
from accounts
where high_priority_tickets_30d >= 3

union all

-- Nobody to talk to: no admin with a working address and consent.
select
    snapshot_date, account_id, 'no_valid_admin',
    emailable_contacts,
    'No admin we can email (' || emailable_contacts || ' other contacts can be emailed)'
from accounts
where not has_valid_admin

union all

-- The churn model's score is above the capacity-based threshold.
select
    snapshot_date, account_id, 'churn_risk_high',
    churn_risk_score,
    'Churn risk ' || cast(round(100 * churn_risk_score) as integer) || '%: ' || churn_top_reasons
from accounts
where churn_risk_high

union all

-- The expansion model's score is above the capacity-based threshold.
select
    snapshot_date, account_id, 'expansion_ready',
    expansion_score,
    'Expansion likelihood ' || cast(round(100 * expansion_score) as integer) || '%: '
        || expansion_top_reasons
from accounts
where expansion_ready
