-- Gold: what happened to each account in the 90 days after each day.
-- One row per account per day. These are the labels the models learn from.
--
-- They come from what the CRM recorded (churn date, closed-won expansion
-- opportunities), exactly as they would in real life. A label can only be used
-- for training once its 90 days have fully passed (outcome_observed = true).

with spine as (

    select account_id, snapshot_date
    from {{ ref('stg_licenses') }}

),

expansions as (

    select account_id, close_date
    from {{ ref('stg_opportunities') }}
    where opportunity_type = 'expansion' and stage = 'closed_won'

),

expanded as (

    select
        spine.account_id,
        spine.snapshot_date,
        count(expansions.close_date) > 0 as expanded_within_90d
    from spine
    left join expansions
        on spine.account_id = expansions.account_id
        and expansions.close_date > spine.snapshot_date
        and expansions.close_date <= {{ days_after('spine.snapshot_date', 90) }}
    group by spine.account_id, spine.snapshot_date

)

select
    spine.account_id,
    spine.snapshot_date,
    ({{ days_after('spine.snapshot_date', 90) }} <= {{ as_of_date() }}) as outcome_observed,
    coalesce(
        accounts.churned_at > spine.snapshot_date
        and accounts.churned_at <= {{ days_after('spine.snapshot_date', 90) }},
        false
    ) as churned_within_90d,
    expanded.expanded_within_90d
from spine
inner join {{ ref('dim_account') }} as accounts
    on spine.account_id = accounts.account_id
inner join expanded
    on spine.account_id = expanded.account_id
    and spine.snapshot_date = expanded.snapshot_date
