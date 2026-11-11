-- Gold: every active account as it stands today. One row per account.
-- The latest row of account_daily, plus segmentation:
--   value tier (rule on ARR)  x  lifecycle stage  x  behaviour cluster (k-means)
-- and the list of signals firing today. The rules engine and the app start here.

{{ config(tags=['scored']) }}

with today as (

    select *
    from {{ ref('account_daily') }}
    where snapshot_date = {{ as_of_date() }}

),

clusters as (

    select * from {{ source('analytics', 'account_clusters') }}

),

signals_today as (

    select
        account_id,
        {{ sorted_text_list('signal_id') }} as signals_firing
    from {{ ref('signals') }}
    where snapshot_date = {{ as_of_date() }}
    group by account_id

)

select
    today.*,
    accounts.region,
    accounts.industry,
    accounts.account_owner,
    accounts.csm,
    accounts.renewal_date,
    case
        when today.arr = 0 then 'free'
        when today.arr < 2000 then 'low'
        when today.arr < 10000 then 'mid'
        else 'high'
    end as value_tier,
    clusters.cluster_name as behaviour_cluster,
    -- comma-separated, in alphabetical order; empty text when nothing is firing
    coalesce(signals_today.signals_firing, '') as signals_firing
from today
inner join {{ ref('dim_account') }} as accounts
    on today.account_id = accounts.account_id
left join clusters
    on today.account_id = clusters.account_id
left join signals_today
    on today.account_id = signals_today.account_id
