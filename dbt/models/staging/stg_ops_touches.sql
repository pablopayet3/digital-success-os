-- Silver: every touch delivered to a customer by a play. One row per touch.

select
    touch_id,
    cast(touch_date as date) as touch_date,
    account_id,
    contact_id,
    play_id,
    enrollment_id,
    step_id,
    channel,
    tier,
    template,
    outcome
from {{ source('bronze', 'ops_touches') }}