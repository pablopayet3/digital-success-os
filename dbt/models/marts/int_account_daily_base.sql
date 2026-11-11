-- Gold (building block): every fact about an account on a given day, joined together.
-- One row per account per day. `account_daily` adds the health score and the
-- lifecycle stage on top of this.
--
-- Contract: contracts/account_daily.yaml

with spine as (

    select
        *,
        cast(snapshot_date + 1 as timestamp) as day_end
    from {{ ref('stg_licenses') }}

),

accounts as (

    select * from {{ ref('dim_account') }}

),

limits as (

    select * from {{ ref('edition_limits') }}

),

-- Usage: today's numbers plus rolling 30-day totals.
usage as (

    select
        snapshot_date,
        account_id,
        active_users,
        mau_30d,
        lag(mau_30d, 30) over by_account as mau_prior_30d,
        sum(active_users) over last_30_days as active_user_days_30d,
        sum(admin_logins) over last_30_days as admin_logins_30d,
        sum(boards_created) over last_30_days as boards_created_30d,
        sum(doc_like_boards_created) over last_60_days as doc_like_boards_60d,
        sum(docs_published) over last_30_days as docs_published_30d,
        sum(assist_invocations) over last_30_days as assist_invocations_30d,
        sum(assist_credits) over last_30_days as assist_credits_30d
    from {{ ref('fct_usage_daily') }}
    window
        by_account as (partition by account_id order by snapshot_date),
        last_30_days as (
            partition by account_id order by snapshot_date
            rows between 29 preceding and current row
        ),
        last_60_days as (
            partition by account_id order by snapshot_date
            rows between 59 preceding and current row
        )

),

-- Running totals that include activity from before the first snapshot.
feature_totals as (

    select
        spine.account_id,
        spine.snapshot_date,
        count(*) filter (where events.event_name = 'automation_rule_created') as automation_rules_total,
        count(*) filter (where events.event_name = 'integration_connected') as integrations_total
    from spine
    left join {{ ref('stg_events') }} as events
        on spine.account_id = events.account_id
        and events.event_date <= spine.snapshot_date
        and events.event_name in ('automation_rule_created', 'integration_connected')
    group by spine.account_id, spine.snapshot_date

),

prerequisites as (

    select * from {{ ref('fct_prerequisites') }}

),

support as (

    select
        spine.account_id,
        spine.snapshot_date,
        count(tickets.ticket_id) filter (
            where tickets.created_date > spine.snapshot_date - 30
        ) as tickets_30d,
        count(tickets.ticket_id) filter (
            where tickets.is_high_priority and tickets.created_date > spine.snapshot_date - 30
        ) as high_priority_tickets_30d,
        count(tickets.ticket_id) filter (
            where tickets.is_high_priority
              and (tickets.resolved_at is null or tickets.resolved_at >= spine.day_end)
        ) as open_high_priority_tickets
    from spine
    left join {{ ref('stg_tickets') }} as tickets
        on spine.account_id = tickets.account_id
        and tickets.created_date <= spine.snapshot_date
    group by spine.account_id, spine.snapshot_date

),

-- The most recent NPS answer on or before each day.
latest_nps as (

    select
        spine.account_id,
        spine.snapshot_date,
        nps.score as latest_nps_score,
        nps.responded_date as latest_nps_date
    from spine
    asof left join {{ ref('stg_nps') }} as nps
        on spine.account_id = nps.account_id
        and spine.day_end > nps.responded_at

),

recent_nps as (

    select
        spine.account_id,
        spine.snapshot_date,
        min(nps.score) as lowest_nps_14d
    from spine
    inner join {{ ref('stg_nps') }} as nps
        on spine.account_id = nps.account_id
        and nps.responded_date between spine.snapshot_date - 13 and spine.snapshot_date
    group by spine.account_id, spine.snapshot_date

),

email as (

    select
        spine.account_id,
        spine.snapshot_date,
        count(sends.send_id) as emails_sent_30d,
        count(sends.opened_at) as emails_opened_30d,
        count(sends.clicked_at) as emails_clicked_30d
    from spine
    left join {{ ref('stg_email_engagement') }} as sends
        on spine.account_id = sends.account_id
        and sends.sent_date between spine.snapshot_date - 29 and spine.snapshot_date
    group by spine.account_id, spine.snapshot_date

),

replies as (

    select
        spine.account_id,
        spine.snapshot_date,
        count(mailbox.message_id) as email_replies_30d
    from spine
    left join {{ ref('stg_mailbox') }} as mailbox
        on spine.account_id = mailbox.account_id
        and mailbox.received_date between spine.snapshot_date - 29 and spine.snapshot_date
    group by spine.account_id, spine.snapshot_date

),

-- Contacts are a current snapshot, so these values are the same for every day.
contacts as (

    select
        account_id,
        count(*) as contacts_total,
        count(*) filter (where can_email) as emailable_contacts,
        coalesce(bool_or(is_valid_admin and can_email), false) as has_valid_admin
    from {{ ref('dim_contact') }}
    group by account_id

)

select
    -- keys
    spine.account_id,
    spine.snapshot_date,

    -- account
    accounts.account_name,
    accounts.segment,
    accounts.coverage_tier,
    spine.edition,
    accounts.has_docs,
    accounts.has_assist,
    accounts.contract_start,
    date_diff('day', accounts.contract_start, spine.snapshot_date) as account_age_days,

    -- seats
    spine.seats_licensed,
    spine.seats_assigned,
    round(spine.seats_assigned / spine.seats_licensed, 4) as seat_utilisation,
    lag(spine.seats_assigned, 30) over (
        partition by spine.account_id order by spine.snapshot_date
    ) as seats_assigned_30d_ago,

    -- usage
    usage.active_users,
    usage.mau_30d,
    usage.mau_prior_30d,
    usage.active_user_days_30d,
    usage.admin_logins_30d,
    usage.boards_created_30d,
    usage.doc_like_boards_60d,
    usage.docs_published_30d,
    usage.assist_invocations_30d,
    usage.assist_credits_30d,
    feature_totals.automation_rules_total,
    feature_totals.integrations_total,

    -- edition limits
    limits.automation_rule_limit,
    limits.integration_limit,
    limits.assist_credits_per_seat * spine.seats_licensed as assist_credits_included,

    -- setup prerequisites, as they stood on the day
    (prerequisites.board_created_on <= spine.snapshot_date) is true as has_first_board,
    (prerequisites.users_invited_on <= spine.snapshot_date) is true as has_five_users,
    (prerequisites.integration_connected_on <= spine.snapshot_date) is true as has_integration,
    (prerequisites.sso_configured_on <= spine.snapshot_date) is true as has_sso,
    (
        ((prerequisites.board_created_on <= spine.snapshot_date) is true)::integer
        + ((prerequisites.users_invited_on <= spine.snapshot_date) is true)::integer
        + ((prerequisites.integration_connected_on <= spine.snapshot_date) is true)::integer
        + ((prerequisites.sso_configured_on <= spine.snapshot_date) is true)::integer
    ) / 4.0 as prerequisite_closure_pct,

    -- support
    support.tickets_30d,
    support.high_priority_tickets_30d,
    support.open_high_priority_tickets,

    -- sentiment
    latest_nps.latest_nps_score,
    latest_nps.latest_nps_date,
    recent_nps.lowest_nps_14d,

    -- contact engagement
    email.emails_sent_30d,
    email.emails_opened_30d,
    email.emails_clicked_30d,
    replies.email_replies_30d,
    coalesce(contacts.contacts_total, 0) as contacts_total,
    coalesce(contacts.emailable_contacts, 0) as emailable_contacts,
    coalesce(contacts.has_valid_admin, false) as has_valid_admin,

    -- commercial
    accounts.arr,
    -- contracts renew every 365 days, so this is exact for past days too
    (365 - date_diff('day', accounts.contract_start, spine.snapshot_date) % 365) % 365 as days_to_renewal,
    accounts.renewal_in_negotiation

from spine
inner join accounts on spine.account_id = accounts.account_id
left join limits on spine.edition = limits.edition
left join usage
    on spine.account_id = usage.account_id and spine.snapshot_date = usage.snapshot_date
left join feature_totals
    on spine.account_id = feature_totals.account_id
    and spine.snapshot_date = feature_totals.snapshot_date
left join prerequisites on spine.account_id = prerequisites.account_id
left join support
    on spine.account_id = support.account_id and spine.snapshot_date = support.snapshot_date
left join latest_nps
    on spine.account_id = latest_nps.account_id
    and spine.snapshot_date = latest_nps.snapshot_date
left join recent_nps
    on spine.account_id = recent_nps.account_id
    and spine.snapshot_date = recent_nps.snapshot_date
left join email
    on spine.account_id = email.account_id and spine.snapshot_date = email.snapshot_date
left join replies
    on spine.account_id = replies.account_id and spine.snapshot_date = replies.snapshot_date
left join contacts on spine.account_id = contacts.account_id
