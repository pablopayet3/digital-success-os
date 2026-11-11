-- Gold: product usage per account per day.
-- MAU (monthly active users) is the number of different users active in the 30 days
-- ending on the snapshot date. Assist credits are the usage-based "consumption".

with spine as (

    select snapshot_date, account_id
    from {{ ref('stg_licenses') }}

),

events as (

    select * from {{ ref('stg_events') }}

),

daily_counts as (

    select
        account_id,
        event_date,
        count(distinct user_id) filter (where event_name = 'user_active') as active_users,
        count(*) filter (where event_name = 'admin_login') as admin_logins,
        count(*) filter (where event_name = 'user_invited') as users_invited,
        count(*) filter (where event_name = 'board_created') as boards_created,
        count(*) filter (
            where event_name = 'board_created'
              and {{ json_text('properties', 'template') }}
                  in ('meeting_notes', 'wiki', 'knowledge_base')
        ) as doc_like_boards_created,
        count(*) filter (where event_name = 'doc_published') as docs_published,
        count(*) filter (where event_name = 'automation_rule_created') as automation_rules_created,
        count(*) filter (where event_name = 'integration_connected') as integrations_connected,
        count(*) filter (where event_name = 'assist_invoked') as assist_invocations,
        coalesce(
            sum(cast({{ json_text('properties', 'credits_used') }} as integer))
                filter (where event_name = 'assist_invoked'),
            0
        ) as assist_credits,
        count(*) as events_total
    from events
    group by account_id, event_date

),

user_days as (

    select distinct account_id, event_date, user_id
    from events
    where event_name = 'user_active'

),

monthly_active as (

    select
        spine.account_id,
        spine.snapshot_date,
        count(distinct user_days.user_id) as mau_30d
    from spine
    left join user_days
        on spine.account_id = user_days.account_id
        and user_days.event_date
            between {{ days_before('spine.snapshot_date', 29) }} and spine.snapshot_date
    group by spine.account_id, spine.snapshot_date

)

select
    spine.snapshot_date,
    spine.account_id,
    coalesce(daily_counts.active_users, 0) as active_users,
    monthly_active.mau_30d,
    coalesce(daily_counts.admin_logins, 0) as admin_logins,
    coalesce(daily_counts.users_invited, 0) as users_invited,
    coalesce(daily_counts.boards_created, 0) as boards_created,
    coalesce(daily_counts.doc_like_boards_created, 0) as doc_like_boards_created,
    coalesce(daily_counts.docs_published, 0) as docs_published,
    coalesce(daily_counts.automation_rules_created, 0) as automation_rules_created,
    coalesce(daily_counts.integrations_connected, 0) as integrations_connected,
    coalesce(daily_counts.assist_invocations, 0) as assist_invocations,
    coalesce(daily_counts.assist_credits, 0) as assist_credits,
    coalesce(daily_counts.events_total, 0) as events_total
from spine
left join daily_counts
    on spine.account_id = daily_counts.account_id
    and spine.snapshot_date = daily_counts.event_date
left join monthly_active
    on spine.account_id = monthly_active.account_id
    and spine.snapshot_date = monthly_active.snapshot_date
