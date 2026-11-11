-- Silver: clean product events. One row per event.
-- Removes duplicate deliveries (same event_id) and events dated in the future
-- (a device with a wrong clock). Late-arriving events are kept: they carry
-- their true date, whichever file they arrived in.

with ranked as (

    select
        *,
        row_number() over (
            partition by event_id
            order by _ingested_at, _source_file
        ) as copy_number
    from {{ source('bronze', 'events') }}

)

select
    event_id,
    occurred_at,
    cast(occurred_at as date) as event_date,
    account_id,
    user_id,
    event_name,
    properties,
    _ingested_at,
    _source_file
from ranked
where copy_number = 1
  and cast(occurred_at as date) <= {{ as_of_date() }}
