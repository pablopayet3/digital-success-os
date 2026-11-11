-- Gold: setup prerequisites per account. One row per account.
-- Four steps: first board, five users with a seat, first integration, SSO.
-- "Prerequisite closure" is the share of the four that are done.
--
-- The five-users step is read from the licence snapshot (the system of record
-- for seats) rather than by counting invite events, because events can be lost.

with first_events as (

    select
        account_id,
        min(event_date) filter (where event_name = 'board_created') as board_created_on,
        min(event_date) filter (where event_name = 'integration_connected') as integration_connected_on,
        min(event_date) filter (where event_name = 'sso_configured') as sso_configured_on
    from {{ ref('stg_events') }}
    group by account_id

),

five_users as (

    select
        account_id,
        min(snapshot_date) as users_invited_on
    from {{ ref('stg_licenses') }}
    where seats_assigned >= 5
    group by account_id

),

steps as (

    select
        accounts.account_id,
        accounts.contract_start,
        accounts.account_age_days as days_since_signup,
        first_events.board_created_on,
        five_users.users_invited_on,
        first_events.integration_connected_on,
        first_events.sso_configured_on
    from {{ ref('dim_account') }} as accounts
    left join first_events on accounts.account_id = first_events.account_id
    left join five_users on accounts.account_id = five_users.account_id

)

select
    *,
    (board_created_on is not null)::integer
        + (users_invited_on is not null)::integer
        + (integration_connected_on is not null)::integer
        + (sso_configured_on is not null)::integer as steps_done,
    (
        (board_created_on is not null)::integer
        + (users_invited_on is not null)::integer
        + (integration_connected_on is not null)::integer
        + (sso_configured_on is not null)::integer
    ) / 4.0 as prerequisite_closure_pct
from steps
