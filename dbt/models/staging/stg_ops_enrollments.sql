-- Silver: play enrolments from the operational store. One row per account per play version.
-- Holdout accounts are enrolled too (arm = 'holdout'): they are the comparison group.

select
    enrollment_id,
    account_id,
    play_id,
    cast(play_version as integer) as play_version,
    arm,
    rollout_stage,
    status,
    exit_reason,
    trigger_signal,
    contact_id,
    highest_tier,
    cast(enrolled_on as date) as enrolled_on,
    cast(closed_on as date) as closed_on
from {{ source('bronze', 'ops_enrollments') }}